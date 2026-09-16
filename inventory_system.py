from __future__ import annotations

import struct
import time
from datetime import datetime
from pathlib import Path

HEADER_STRUCT = struct.Struct('<4sHHIIIIQ')
ITEM_STRUCT = struct.Struct('<I I 32s 16s 12s I I f B 3x')
CATEGORY_STRUCT = struct.Struct('<I 24s 80s B 3x')
MOVEMENT_STRUCT = struct.Struct('<Q I B I I f 32s 16s B 3x')
APP_VERSION = '1.0'


class InventorySystem:
    def __init__(self, base_dir: str = '.'):
        self.base_dir = Path(base_dir)
        self.items_path = self.base_dir / 'items.dat'
        self.categories_path = self.base_dir / 'categories.dat'
        self.movements_path = self.base_dir / 'movements.dat'
        self.report_path = self.base_dir / 'report.txt'

        self.base_dir.mkdir(parents=True, exist_ok=True)

        self._ensure_file(self.items_path, b'ITEM', ITEM_STRUCT.size)
        self._ensure_file(self.categories_path, b'CATE', CATEGORY_STRUCT.size)
        self._ensure_file(self.movements_path, b'MOVE', MOVEMENT_STRUCT.size)

        self.items = self._load_items()
        self.categories = self._load_categories()
        self.movements = self._load_movements()

        if not self.categories:
            self._seed_default_categories()
            self.categories = self._load_categories()

    def _ensure_file(self, path: Path, magic: bytes, record_size: int) -> None:
        if not path.exists() or path.stat().st_size < HEADER_STRUCT.size:
            self._write_header(path, magic, record_size, 0, 0, 0, 0xFFFFFFFF, int(time.time()))
            return

        with path.open('rb') as fh:
            data = fh.read(HEADER_STRUCT.size)

        if len(data) < HEADER_STRUCT.size:
            self._write_header(path, magic, record_size, 0, 0, 0, 0xFFFFFFFF, int(time.time()))
            return

        file_magic, version, file_record_size, record_count, active_count, deleted_count, free_head, created_ts = HEADER_STRUCT.unpack(data)
        if file_magic != magic:
            raise ValueError(f'{path.name}: magic code ไม่ถูกต้อง')
        if version != 1:
            raise ValueError(f'{path.name}: version ไม่รองรับ')
        if file_record_size != record_size:
            raise ValueError(f'{path.name}: record size ไม่ตรงกับรูปแบบที่กำหนด')

        expected_size = HEADER_STRUCT.size + (record_count * record_size)
        if path.stat().st_size < expected_size:
            raise ValueError(f'{path.name}: ไฟล์เสียหายหรือสั้นกว่าขนาดที่คาดไว้')

    def _write_header(self, path: Path, magic: bytes, record_size: int, record_count: int, active_count: int, deleted_count: int, free_head: int, created_ts: int) -> None:
        header = HEADER_STRUCT.pack(magic, 1, record_size, record_count, active_count, deleted_count, free_head, created_ts)
        with path.open('wb') as fh:
            fh.write(header)

    def _read_header(self, path: Path):
        if not path.exists() or path.stat().st_size < HEADER_STRUCT.size:
            return None
        with path.open('rb') as fh:
            data = fh.read(HEADER_STRUCT.size)
        if len(data) < HEADER_STRUCT.size:
            return None
        return HEADER_STRUCT.unpack(data)

    def _load_items(self):
        return self._load_records(self.items_path, ITEM_STRUCT, b'ITEM', 'item')

    def _load_categories(self):
        return self._load_records(self.categories_path, CATEGORY_STRUCT, b'CATE', 'category')

    def _load_movements(self):
        return self._load_records(self.movements_path, MOVEMENT_STRUCT, b'MOVE', 'movement')

    def _load_records(self, path: Path, record_struct: struct.Struct, expected_magic: bytes, record_type: str):
        if not path.exists() or path.stat().st_size < HEADER_STRUCT.size:
            return []

        header = self._read_header(path)
        if header is None:
            return []

        magic, version, record_size, record_count, active_count, deleted_count, free_head, created_ts = header
        if magic != expected_magic:
            raise ValueError(f'{path.name}: magic code ไม่ถูกต้อง')
        if record_size != record_struct.size:
            raise ValueError(f'{path.name}: record size ไม่ตรงกับรูปแบบที่กำหนด')

        with path.open('rb') as fh:
            payload = fh.read()

        records = []
        for idx in range(record_count):
            start = HEADER_STRUCT.size + idx * record_size
            end = start + record_size
            if end > len(payload):
                break
            raw = payload[start:end]
            if raw == b'\x00' * record_size:
                records.append(None)
                continue

            if record_type == 'item':
                item_id, category_id, name, unit, location, quantity, reorder_level, unit_price, status = record_struct.unpack(raw)
                records.append({
                    'item_id': item_id,
                    'category_id': category_id,
                    'name': self._decode_fixed(name),
                    'unit': self._decode_fixed(unit),
                    'location': self._decode_fixed(location),
                    'quantity': quantity,
                    'reorder_level': reorder_level,
                    'unit_price': float(unit_price),
                    'status': status,
                })
            elif record_type == 'category':
                category_id, name, description, status = record_struct.unpack(raw)
                records.append({
                    'category_id': category_id,
                    'name': self._decode_fixed(name),
                    'description': self._decode_fixed(description),
                    'status': status,
                })
            else:
                timestamp, log_seq, op_code, item_id, quantity, balance, operator, note, status_after = record_struct.unpack(raw)
                records.append({
                    'timestamp': timestamp,
                    'log_seq': log_seq,
                    'op_code': op_code,
                    'item_id': item_id,
                    'quantity': quantity,
                    'balance': float(balance),
                    'operator': self._decode_fixed(operator),
                    'note': self._decode_fixed(note),
                    'status_after': status_after,
                })

        return records

    def _seed_default_categories(self) -> None:
        defaults = [
            (1, 'เครื่องเขียน', 'วัสดุสำหรับงานสำนักงานและห้องเรียน', 1),
            (2, 'อุปกรณ์สำนักงาน', 'เครื่องใช้สำนักงานต่าง ๆ', 1),
            (3, 'คอมพิวเตอร์', 'อุปกรณ์คอมพิวเตอร์และอุปกรณ์ต่อพ่วง', 1),
            (4, 'เฟอร์นิเจอร์', 'โต๊ะ เก้าอี้ และอุปกรณ์ภายในห้อง', 1),
            (5, 'โทรคมนาคม', 'อุปกรณ์สื่อสารและเครือข่าย', 1),
            (6, 'อุปกรณ์ไฟฟ้า', 'หลอดไฟ เครื่องใช้ไฟฟ้า ฯลฯ', 1),
            (7, 'ซ่อมบำรุง', 'วัสดุสำหรับซ่อมและบำรุงรักษา', 1),
            (8, 'งานพิมพ์และเอกสาร', 'กระดาษและอุปกรณ์ประมวลผลเอกสาร', 1),
        ]
        self.categories = []
        for category_id, name, desc, status in defaults:
            self.categories.append({
                'category_id': category_id,
                'name': name,
                'description': desc,
                'status': status,
            })
        self._save_categories()

    def _decode_fixed(self, raw: bytes) -> str:
        if not raw:
            return ''
        text = raw.split(b'\x00', 1)[0].decode('utf-8', errors='ignore')
        return text.strip()

    def _encode_fixed(self, value: str, size: int) -> bytes:
        if value is None:
            value = ''
        encoded = value.encode('utf-8', errors='ignore')
        if len(encoded) > size:
            encoded = encoded[:size]
        return encoded.ljust(size, b'\x00')

    def _save_items(self) -> None:
        active_count = sum(1 for item in self.items if item and item.get('status') == 1)
        deleted_count = sum(1 for item in self.items if item and item.get('status') == 0)
        record_count = len(self.items)

        with self.items_path.open('wb') as fh:
            fh.write(HEADER_STRUCT.pack(b'ITEM', 1, ITEM_STRUCT.size, record_count, active_count, deleted_count, 0xFFFFFFFF, int(time.time())))
            for item in self.items:
                if item is None:
                    fh.write(b'\x00' * ITEM_STRUCT.size)
                    continue
                fh.write(ITEM_STRUCT.pack(
                    int(item.get('item_id', 0)),
                    int(item.get('category_id', 0)),
                    self._encode_fixed(item.get('name', ''), 32),
                    self._encode_fixed(item.get('unit', ''), 16),
                    self._encode_fixed(item.get('location', ''), 12),
                    int(item.get('quantity', 0)),
                    int(item.get('reorder_level', 0)),
                    float(item.get('unit_price', 0.0)),
                    int(item.get('status', 1)),
                ))

    def _save_categories(self) -> None:
        active_count = sum(1 for category in self.categories if category and category.get('status') == 1)
        deleted_count = sum(1 for category in self.categories if category and category.get('status') == 0)
        record_count = len(self.categories)

        with self.categories_path.open('wb') as fh:
            fh.write(HEADER_STRUCT.pack(b'CATE', 1, CATEGORY_STRUCT.size, record_count, active_count, deleted_count, 0xFFFFFFFF, int(time.time())))
            for category in self.categories:
                if category is None:
                    fh.write(b'\x00' * CATEGORY_STRUCT.size)
                    continue
                fh.write(CATEGORY_STRUCT.pack(
                    int(category.get('category_id', 0)),
                    self._encode_fixed(category.get('name', ''), 24),
                    self._encode_fixed(category.get('description', ''), 80),
                    int(category.get('status', 1)),
                ))

    def _save_movements(self) -> None:
        record_count = len(self.movements)
        with self.movements_path.open('wb') as fh:
            fh.write(HEADER_STRUCT.pack(b'MOVE', 1, MOVEMENT_STRUCT.size, record_count, record_count, 0, 0xFFFFFFFF, int(time.time())))
            for move in self.movements:
                fh.write(MOVEMENT_STRUCT.pack(
                    int(move.get('timestamp', int(time.time()))),
                    int(move.get('log_seq', 0)),
                    int(move.get('op_code', 0)),
                    int(move.get('item_id', 0)),
                    int(move.get('quantity', 0)),
                    float(move.get('balance', 0.0)),
                    self._encode_fixed(move.get('operator', ''), 32),
                    self._encode_fixed(move.get('note', ''), 16),
                    int(move.get('status_after', 1)),
                ))

    def _find_item_index(self, item_id: int) -> int:
        for idx, item in enumerate(self.items):
            if item and item.get('item_id') == item_id:
                return idx
        return -1

    def _find_category_index(self, category_id: int) -> int:
        for idx, category in enumerate(self.categories):
            if category and category.get('category_id') == category_id:
                return idx
        return -1

    def _get_item(self, item_id: int):
        idx = self._find_item_index(item_id)
        if idx == -1:
            return None
        return self.items[idx]

    def _log_movement(self, op_code: int, item_id: int, quantity: int, balance: float, operator: str, note: str, status_after: int) -> None:
        self.movements.append({
            'timestamp': int(time.time()),
            'log_seq': len(self.movements) + 1,
            'op_code': op_code,
            'item_id': item_id,
            'quantity': quantity,
            'balance': float(balance),
            'operator': operator,
            'note': note,
            'status_after': status_after,
        })
        self._save_movements()

    def _prompt_int(self, prompt: str, *, positive: bool = False, minimum: int = 0, maximum: int | None = None, allow_blank: bool = False) -> int:
        while True:
            value = input(prompt).strip()
            if value == '' and allow_blank:
                return minimum
            try:
                number = int(value)
            except ValueError:
                print('กรุณากรอกเป็นจำนวนเต็มเท่านั้น')
                continue
            if positive and number <= 0:
                print('ค่าต้องเป็นจำนวนเต็มบวก')
                continue
            if number < minimum:
                print(f'ค่าต้องไม่น้อยกว่า {minimum}')
                continue
            if maximum is not None and number > maximum:
                print(f'ค่าต้องไม่เกิน {maximum}')
                continue
            return number

    def _prompt_float(self, prompt: str, *, minimum: float = 0.0, positive: bool = False, allow_blank: bool = False) -> float:
        while True:
            value = input(prompt).strip()
            if value == '' and allow_blank:
                return minimum
            try:
                number = float(value)
            except ValueError:
                print('กรุณากรอกเป็นตัวเลขทศนิยมเท่านั้น')
                continue
            if positive and number <= 0:
                print('ค่าต้องมากกว่า 0')
                continue
            if number < minimum:
                print(f'ค่าต้องไม่น้อยกว่า {minimum}')
                continue
            return number

    def _prompt_text(self, prompt: str, *, max_bytes: int, allow_blank: bool = False) -> str:
        while True:
            value = input(prompt).strip()
            if value == '' and allow_blank:
                return ''
            if value == '':
                print('กรุณากรอกข้อความ')
                continue
            if len(value.encode('utf-8')) > max_bytes:
                print(f'ข้อความยาวเกิน {max_bytes} bytes')
                continue
            return value

    def add_item(self) -> None:
        print('\n--- เพิ่มรายการพัสดุ ---')
        item_id = self._prompt_int('รหัสพัสดุ (item_id): ', positive=True)
        if self._get_item(item_id) is not None:
            print('ผิดพลาด: รหัสพัสดุซ้ำ')
            return

        category_id = self._prompt_int('รหัสหมวดหมู่ (category_id): ', positive=True)
        if self._find_category_index(category_id) == -1:
            print('ผิดพลาด: ไม่พบหมวดหมู่ที่ระบุ')
            return

        name = self._prompt_text('ชื่อพัสดุ: ', max_bytes=32)
        unit = self._prompt_text('หน่วยนับ: ', max_bytes=16)
        location = self._prompt_text('สถานที่จัดเก็บ: ', max_bytes=12)
        quantity = self._prompt_int('จำนวนคงเหลือ: ', minimum=0)
        reorder_level = self._prompt_int('จุดสั่งซื้อขั้นต่ำ: ', minimum=0)
        unit_price = self._prompt_float('ราคาต่อหน่วย: ', minimum=0.0)

        new_item = {
            'item_id': item_id,
            'category_id': category_id,
            'name': name,
            'unit': unit,
            'location': location,
            'quantity': quantity,
            'reorder_level': reorder_level,
            'unit_price': unit_price,
            'status': 1,
        }

        slot_index = -1
        for idx, current in enumerate(self.items):
            if current is None or (current and current.get('status') == 0):
                slot_index = idx
                break

        if slot_index == -1:
            self.items.append(new_item)
        else:
            self.items[slot_index] = new_item

        self._save_items()
        self._log_movement(1, item_id, quantity, quantity, 'ADMIN', 'ADD', 1)
        print(f'เพิ่มพัสดุ "{name}" สำเร็จ')

    def update_item(self) -> None:
        print('\n--- แก้ไขรายการพัสดุ ---')
        item_id = self._prompt_int('ระบุ item_id ที่ต้องการแก้ไข: ', positive=True)
        item = self._get_item(item_id)
        if item is None:
            print('ไม่พบพัสดุที่ระบุ')
            return
        if item.get('status') != 1:
            print('พัสดุนี้ถูกลบแล้ว ไม่สามารถแก้ไขได้')
            return

        print('เว้นว่างไว้เพื่อคงค่าเดิม')
        name = self._prompt_text(f'ชื่อพัสดุ [{item["name"]}]: ', max_bytes=32, allow_blank=True)
        if name:
            item['name'] = name

        category_id = self._prompt_int(f'รหัสหมวดหมู่ [{item["category_id"]}] (กด 0 เพื่อคงค่า): ', minimum=0, maximum=999999)
        if category_id > 0:
            if self._find_category_index(category_id) == -1:
                print('ผิดพลาด: ไม่พบหมวดหมู่ที่ระบุ')
                return
            item['category_id'] = category_id

        unit = self._prompt_text(f'หน่วยนับ [{item["unit"]}]: ', max_bytes=16, allow_blank=True)
        if unit:
            item['unit'] = unit

        location = self._prompt_text(f'สถานที่จัดเก็บ [{item["location"]}]: ', max_bytes=12, allow_blank=True)
        if location:
            item['location'] = location

        reorder_level = self._prompt_int(f'จุดสั่งซื้อขั้นต่ำ [{item["reorder_level"]}] (กด -1 เพื่อคงค่า): ', minimum=-1)
        if reorder_level >= 0:
            item['reorder_level'] = reorder_level

        unit_price = self._prompt_float(f'ราคาต่อหน่วย [{item["unit_price"]}] (กด -1 เพื่อคงค่า): ', minimum=-1.0)
        if unit_price >= 0:
            item['unit_price'] = unit_price

        self._save_items()
        self._log_movement(2, item_id, 0, item['quantity'], 'ADMIN', 'UPDATE', 1)
        print('อัปเดตข้อมูลสำเร็จ')

    def delete_item(self) -> None:
        print('\n--- ลบรายการพัสดุ (Logical Delete) ---')
        item_id = self._prompt_int('ระบุ item_id ที่ต้องการลบ: ', positive=True)
        item = self._get_item(item_id)
        if item is None:
            print('ไม่พบพัสดุที่ระบุ')
            return
        if item.get('status') == 0:
            print('พัสดุนี้ถูกลบแล้ว')
            return

        if item.get('quantity', 0) > 0:
            confirm = input('พัสดุนี้ยังคงมีจำนวนคงเหลือ อยากลบต่อหรือไม่? [y/N]: ').strip().lower()
            if confirm not in ('y', 'yes'):
                print('ยกเลิกการลบ')
                return

        item['status'] = 0
        self._save_items()
        self._log_movement(3, item_id, item['quantity'], item['quantity'], 'ADMIN', 'DELETE', 0)
        print(f'ลบพัสดุ {item_id} สำเร็จ (logical delete)')

    def view_one(self) -> None:
        item_id = self._prompt_int('ระบุ item_id: ', positive=True)
        item = self._get_item(item_id)
        if item is None:
            print('ไม่พบข้อมูล')
            return
        self._print_item(item)

    def view_all(self) -> None:
        active_items = [item for item in self.items if item and item.get('status') == 1]
        if not active_items:
            print('ไม่มีข้อมูลพัสดุ Active')
            return

        print('\nรายการพัสดุทั้งหมด')
        print(f"{'ID':<8}{'หมวด':<12}{'ชื่อ':<20}{'จำนวน':>8}{'ขั้นต่ำ':>8}{'ราคา':>12}{'สถานะ':>8}")
        for item in active_items:
            print(f"{item['item_id']:<8}{item['category_id']:<12}{item['name']:<20}{item['quantity']:>8}{item['reorder_level']:>8}{item['unit_price']:>12.2f}{'Active':>8}")

    def filter_items(self) -> None:
        print('1) ตามหมวดหมู่')
        print('2) ตามสถานะ')
        mode = input('เลือก: ').strip()

        if mode == '1':
            category_id = self._prompt_int('ระบุ category_id: ', positive=True)
            matches = [item for item in self.items if item and item.get('category_id') == category_id]
        elif mode == '2':
            status = self._prompt_int('สถานะ (1=Active, 0=Deleted): ', minimum=0, maximum=1)
            matches = [item for item in self.items if item and item.get('status') == status]
        else:
            print('ตัวเลือกไม่ถูกต้อง')
            return

        if not matches:
            print('ไม่มีข้อมูลที่ตรงเงื่อนไข')
            return

        for item in matches:
            self._print_item(item)

    def search_by_name(self) -> None:
        keyword = input('ค้นหาชื่อพัสดุ: ').strip()
        if not keyword:
            print('ต้องระบุคำค้นหา')
            return

        matches = [item for item in self.items if item and keyword.lower() in item.get('name', '').lower()]
        if not matches:
            print('ไม่พบข้อมูล')
            return

        for item in matches:
            self._print_item(item)

    def low_stock_items(self) -> None:
        matches = [item for item in self.items if item and item.get('status') == 1 and item.get('quantity', 0) <= item.get('reorder_level', 0)]
        if not matches:
            print('ไม่มีรายการใกล้หมด')
            return

        for item in matches:
            self._print_item(item)

    def summary_stats(self) -> None:
        active_items = [item for item in self.items if item and item.get('status') == 1]
        deleted_items = [item for item in self.items if item and item.get('status') == 0]
        total_quantity = sum(item.get('quantity', 0) for item in active_items)
        total_value = sum(item.get('quantity', 0) * item.get('unit_price', 0.0) for item in active_items)
        low_count = sum(1 for item in active_items if item.get('quantity', 0) <= item.get('reorder_level', 0))

        print('\nสถิติคลังพัสดุ')
        print(f'Active items: {len(active_items)}')
        print(f'Deleted items: {len(deleted_items)}')
        print(f'Total quantity: {total_quantity}')
        print(f'Total inventory value: {total_value:.2f} THB')
        print(f'Low-stock items: {low_count}')

    def view_menu(self) -> None:
        while True:
            print('\n===== เมนู View =====')
            print('1) ดูรายการเดียว')
            print('2) ดูทั้งหมด')
            print('3) กรองตามหมวดหมู่หรือสถานะ')
            print('4) ค้นหาจากชื่อพัสดุ')
            print('5) ดูรายการที่ใกล้หมด')
            print('6) สถิติโดยสรุป')
            print('0) กลับสู่เมนูหลัก')
            choice = input('เลือกเมนู: ').strip()

            if choice == '1':
                self.view_one()
            elif choice == '2':
                self.view_all()
            elif choice == '3':
                self.filter_items()
            elif choice == '4':
                self.search_by_name()
            elif choice == '5':
                self.low_stock_items()
            elif choice == '6':
                self.summary_stats()
            elif choice == '0':
                return
            else:
                print('เมนูไม่ถูกต้อง')

    def stock_movement(self) -> None:
        print('\n--- Stock Movement ---')
        item_id = self._prompt_int('ระบุ item_id: ', positive=True)
        item = self._get_item(item_id)
        if item is None:
            print('ไม่พบพัสดุ')
            return
        if item.get('status') != 1:
            print('พัสดุถูกลบแล้ว')
            return

        op = input('ประเภท (RECEIVE/ISSUE): ').strip().upper()
        if op not in ('RECEIVE', 'ISSUE'):
            print('ประเภทไม่ถูกต้อง')
            return

        quantity = self._prompt_int('จำนวน: ', minimum=1)
        if op == 'ISSUE' and quantity > item['quantity']:
            print('ไม่สามารถเบิกเกินจำนวนคงเหลือ')
            return

        if op == 'RECEIVE':
            item['quantity'] += quantity
            op_code = 4
            note = 'RECEIVE'
        else:
            item['quantity'] -= quantity
            op_code = 5
            note = 'ISSUE'

        self._save_items()
        self._log_movement(op_code, item_id, quantity, item['quantity'], 'ADMIN', note, 1)
        print(f'ปรับยอดสำเร็จ: item_id={item_id}, ยอดปัจจุบัน={item["quantity"]}')

    def generate_report(self) -> None:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        active_items = [item for item in self.items if item and item.get('status') == 1]
        deleted_items = [item for item in self.items if item and item.get('status') == 0]
        total_quantity = sum(item.get('quantity', 0) for item in active_items)
        total_value = sum(item.get('quantity', 0) * item.get('unit_price', 0.0) for item in active_items)
        low_items = [item for item in active_items if item.get('quantity', 0) <= item.get('reorder_level', 0)]

        category_summary = {}
        for item in active_items:
            category_name = self._get_category_name(item['category_id'])
            category_summary[category_name] = category_summary.get(category_name, 0) + 1

        lines = []
        lines.append('Inventory Management System - Summary Report')
        lines.append(f'Generated At : {timestamp}')
        lines.append(f'App Version  : {APP_VERSION}')
        lines.append('Endianness   : Little-Endian')
        lines.append('Encoding     : UTF-8 (fixed-length binary records)')
        lines.append('')
        lines.append('File Status')
        lines.append('- items.dat       : OK')
        lines.append('- categories.dat  : OK')
        lines.append('- movements.dat   : OK')
        lines.append('')
        lines.append('Record Summary')
        lines.append(f'- Item records (allocated) : {len(self.items)}')
        lines.append(f'- Active items             : {len(active_items)}')
        lines.append(f'- Deleted items            : {len(deleted_items)}')
        lines.append(f'- Free slots               : {len([slot for slot in self.items if slot is None])}')
        lines.append(f'- Categories               : {len([cat for cat in self.categories if cat and cat.get("status") == 1])}')
        lines.append(f'- Movement records         : {len(self.movements)}')
        lines.append('')
        lines.append('Inventory Summary')
        lines.append(f'- Total quantity           : {total_quantity}')
        lines.append(f'- Total inventory value    : {total_value:,.2f} THB')
        lines.append(f'- Low-stock items          : {len(low_items)}')
        lines.append('')
        lines.append('Items by Category')
        if category_summary:
            for name, count in sorted(category_summary.items()):
                lines.append(f'- {name:<20} : {count}')
        else:
            lines.append('- ไม่มีข้อมูลหมวดหมู่')
        lines.append('')
        lines.append('Latest Activities')
        for move in reversed(self.movements[-5:]):
            dt = datetime.fromtimestamp(move['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            lines.append(f'- [{dt}] {move["note"]} item={move["item_id"]} quantity={move["quantity"]}')

        self.report_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print(f'สร้างรายงานเรียบร้อยแล้ว: {self.report_path}')

    def _get_category_name(self, category_id: int) -> str:
        for category in self.categories:
            if category and category.get('category_id') == category_id:
                return category.get('name', 'Unknown')
        return 'Unknown'

    def _print_item(self, item) -> None:
        print(f"ID={item['item_id']} | Category={item['category_id']} | Name={item['name']} | Qty={item['quantity']} | Reorder={item['reorder_level']} | Price={item['unit_price']:.2f} | Status={item['status']}")

    def main_menu(self) -> str:
        print('\n===== ระบบคลังพัสดุและครุภัณฑ์ =====')
        print('1) Add Item')
        print('2) Update Item')
        print('3) Delete Item')
        print('4) View')
        print('5) Stock Movement')
        print('6) Generate Report')
        print('0) Exit')
        return input('เลือกเมนู: ').strip()

    def run(self) -> None:
        while True:
            choice = self.main_menu()
            if choice == '1':
                self.add_item()
            elif choice == '2':
                self.update_item()
            elif choice == '3':
                self.delete_item()
            elif choice == '4':
                self.view_menu()
            elif choice == '5':
                self.stock_movement()
            elif choice == '6':
                self.generate_report()
            elif choice == '0':
                self.generate_report()
                print('ออกจากระบบเรียบร้อยแล้ว')
                break
            else:
                print('เมนูไม่ถูกต้อง กรุณาเลือกใหม่')


def main() -> None:
    app = InventorySystem('.')
    app.run()


if __name__ == '__main__':
    main()
