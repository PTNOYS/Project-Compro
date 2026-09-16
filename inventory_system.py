from __future__ import annotations

import os
import struct
import time
from datetime import datetime
from pathlib import Path

HEADER_STRUCT = struct.Struct('<4sHHIIIIQ')
ITEM_STRUCT = struct.Struct('<I I 32s 16s 12s I I f B 3x')
CATEGORY_STRUCT = struct.Struct('<I 24s 80s B 3x')
MOVEMENT_STRUCT = struct.Struct('<Q I B I I f 32s 16s B 3x')


class InventorySystem:
    def __init__(self, base_dir: str = '.'):
        self.base_dir = Path(base_dir)
        self.items_path = self.base_dir / 'items.dat'
        self.categories_path = self.base_dir / 'categories.dat'
        self.movements_path = self.base_dir / 'movements.dat'
        self.report_path = self.base_dir / 'report.txt'

        self._ensure_file(self.items_path, b'ITEM', ITEM_STRUCT.size)
        self._ensure_file(self.categories_path, b'CATE', CATEGORY_STRUCT.size)
        self._ensure_file(self.movements_path, b'MOVE', MOVEMENT_STRUCT.size)

        self.items = self._load_items()
        self.categories = self._load_categories()
        self.movements = self._load_movements()

        if not self.categories or all(cat is None for cat in self.categories):
            self._seed_default_categories()
        self.categories = self._load_categories()

    def _ensure_file(self, path: Path, magic: bytes, record_size: int):
        if not path.exists() or path.stat().st_size < HEADER_STRUCT.size:
            self._write_header(path, magic, record_size, 0, 0, 0, 0xFFFFFFFF, int(time.time()))
            return

        try:
            with path.open('rb') as f:
                raw = f.read(HEADER_STRUCT.size)
            if len(raw) < HEADER_STRUCT.size:
                self._write_header(path, magic, record_size, 0, 0, 0, 0xFFFFFFFF, int(time.time()))
                return

            file_magic, version, file_record_size, record_count, active_count, deleted_count, free_head, created_ts = HEADER_STRUCT.unpack(raw)
            if file_magic != magic:
                raise ValueError(f'{path.name}: magic code ไม่ถูกต้อง')
            if version != 1:
                raise ValueError(f'{path.name}: version ไม่รองรับ')
            if file_record_size != record_size:
                raise ValueError(f'{path.name}: record size ไม่ตรงกับรูปแบบที่กำหนด')
            expected_size = HEADER_STRUCT.size + (record_count * record_size)
            if path.stat().st_size < expected_size:
                raise ValueError(f'{path.name}: ไฟล์เสียหรือสั้นกว่าขนาดระเบียนที่กำหนด')
        except Exception:
            raise ValueError(f'{path.name}: ไฟล์ข้อมูลเสียหาย ไม่สามารถเปิดใช้งานได้')

    def _write_header(self, path: Path, magic: bytes, record_size: int, record_count: int, active_count: int, deleted_count: int, free_head: int, created_ts: int):
        header = HEADER_STRUCT.pack(magic, 1, record_size, record_count, active_count, deleted_count, free_head, created_ts)
        path.write_bytes(header)

    def _read_header(self, path: Path):
        if not path.exists() or path.stat().st_size < HEADER_STRUCT.size:
            return None
        with path.open('rb') as f:
            raw = f.read(HEADER_STRUCT.size)
        if len(raw) < HEADER_STRUCT.size:
            return None
        return HEADER_STRUCT.unpack(raw)

    def _load_items(self):
        return self._load_records(self.items_path, ITEM_STRUCT, b'ITEM', 'item')

    def _load_categories(self):
        return self._load_records(self.categories_path, CATEGORY_STRUCT, b'CATE', 'category')

    def _load_movements(self):
        return self._load_records(self.movements_path, MOVEMENT_STRUCT, b'MOVE', 'movement')

    def _load_records(self, path: Path, record_struct: struct.Struct, expected_magic: bytes, kind: str):
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

        data = path.read_bytes()
        records = []
        for idx in range(record_count):
            offset = HEADER_STRUCT.size + idx * record_size
            if offset + record_size > len(data):
                break
            raw = data[offset:offset + record_size]
            if raw == b'\x00' * record_size:
                records.append(None)
                continue
            if kind == 'item':
                item_id, category_id, name, unit, location, quantity, reorder_level, unit_price, status = record_struct.unpack(raw)
                records.append({
                    'item_id': item_id,
                    'category_id': category_id,
                    'name': self._decode_string(name),
                    'unit': self._decode_string(unit),
                    'location': self._decode_string(location),
                    'quantity': quantity,
                    'reorder_level': reorder_level,
                    'unit_price': float(unit_price),
                    'status': status,
                })
            elif kind == 'category':
                category_id, name, description, status = record_struct.unpack(raw)
                records.append({
                    'category_id': category_id,
                    'name': self._decode_string(name),
                    'description': self._decode_string(description),
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
                    'operator': self._decode_string(operator),
                    'note': self._decode_string(note),
                    'status_after': status_after,
                })
        return records

    def _seed_default_categories(self):
        default_categories = [
            (1, 'เครื่องเขียน', 'วัสดุเบิกใช้ในสำนักงานและห้องเรียน', 1),
            (2, 'อุปกรณ์สำนักงาน', 'อุปกรณ์ที่ใช้ประจำสำนักงาน', 1),
            (3, 'คอมพิวเตอร์', 'อุปกรณ์คอมพิวเตอร์และอุปกรณ์ต่อพ่วง', 1),
            (4, 'เฟอร์นิเจอร์', 'โต๊ะ เก้าอี้ และอุปกรณ์ภายในห้อง', 1),
            (5, 'โทรคมนาคม', 'อุปกรณ์สื่อสารและเครือข่าย', 1),
            (6, 'อุปกรณ์ไฟฟ้า', 'หลอดไฟ เครื่องใช้ไฟฟ้า ฯลฯ', 1),
            (7, 'ซ่อมบำรุง', 'วัสดุสำหรับซ่อมและบำรุงรักษา', 1),
            (8, 'งานพิมพ์และเอกสาร', 'กระดาษและอุปกรณ์ประมวลผลเอกสาร', 1),
        ]
        self.categories = []
        for category_id, name, desc, status in default_categories:
            self.categories.append({
                'category_id': category_id,
                'name': name,
                'description': desc,
                'status': status,
            })
        self._save_categories()

    def _decode_string(self, raw_value: bytes) -> str:
        if not raw_value:
            return ''
        return raw_value.split(b'\x00', 1)[0].decode('utf-8', errors='ignore').strip()

    def _encode_string(self, value: str, size: int) -> bytes:
        if value is None:
            value = ''
        raw = value.encode('utf-8', errors='ignore')
        if len(raw) > size:
            raw = raw[:size]
        return raw.ljust(size, b'\x00')

    def _find_item_index(self, item_id: int):
        for idx, item in enumerate(self.items):
            if item and item.get('item_id') == item_id:
                return idx
        return -1

    def _find_category_index(self, category_id: int):
        for idx, category in enumerate(self.categories):
            if category and category.get('category_id') == category_id:
                return idx
        return -1

    def _save_items(self):
        data = bytearray()
        active_count = sum(1 for item in self.items if item and item.get('status') == 1)
        deleted_count = sum(1 for item in self.items if item and item.get('status') == 0)
        free_head = self._get_free_head(self.items)
        data.extend(HEADER_STRUCT.pack(b'ITEM', 1, ITEM_STRUCT.size, len(self.items), active_count, deleted_count, free_head, int(time.time())))
        for item in self.items:
            if item is None:
                data.extend(b'\x00' * ITEM_STRUCT.size)
                continue
            payload = ITEM_STRUCT.pack(
                int(item.get('item_id', 0)),
                int(item.get('category_id', 0)),
                self._encode_string(item.get('name', ''), 32),
                self._encode_string(item.get('unit', ''), 16),
                self._encode_string(item.get('location', ''), 12),
                int(item.get('quantity', 0)),
                int(item.get('reorder_level', 0)),
                float(item.get('unit_price', 0.0)),
                int(item.get('status', 1)),
            )
            data.extend(payload)
        self.items_path.write_bytes(data)

    def _save_categories(self):
        data = bytearray()
        active_count = sum(1 for category in self.categories if category and category.get('status') == 1)
        deleted_count = sum(1 for category in self.categories if category and category.get('status') == 0)
        free_head = self._get_free_head(self.categories)
        data.extend(HEADER_STRUCT.pack(b'CATE', 1, CATEGORY_STRUCT.size, len(self.categories), active_count, deleted_count, free_head, int(time.time())))
        for category in self.categories:
            if category is None:
                data.extend(b'\x00' * CATEGORY_STRUCT.size)
                continue
            payload = CATEGORY_STRUCT.pack(
                int(category.get('category_id', 0)),
                self._encode_string(category.get('name', ''), 24),
                self._encode_string(category.get('description', ''), 80),
                int(category.get('status', 1)),
            )
            data.extend(payload)
        self.categories_path.write_bytes(data)

    def _save_movements(self):
        data = bytearray()
        record_count = len(self.movements)
        active_count = record_count
        data.extend(HEADER_STRUCT.pack(b'MOVE', 1, MOVEMENT_STRUCT.size, record_count, active_count, 0, 0xFFFFFFFF, int(time.time())))
        for move in self.movements:
            payload = MOVEMENT_STRUCT.pack(
                int(move.get('timestamp', int(time.time()))),
                int(move.get('log_seq', 0)),
                int(move.get('op_code', 0)),
                int(move.get('item_id', 0)),
                int(move.get('quantity', 0)),
                float(move.get('balance', 0.0)),
                self._encode_string(move.get('operator', ''), 32),
                self._encode_string(move.get('note', ''), 16),
                int(move.get('status_after', 1)),
            )
            data.extend(payload)
        self.movements_path.write_bytes(data)

    def _get_free_head(self, slots):
        for idx, slot in enumerate(slots):
            if slot is None or slot.get('status') == 0:
                return idx
        return 0xFFFFFFFF

    def _log_movement(self, op_code: int, item_id: int, quantity: int, balance: float, operator: str, note: str, status_after: int):
        if self.movements is None:
            self.movements = []
        log_seq = len(self.movements) + 1
        self.movements.append({
            'timestamp': int(time.time()),
            'log_seq': log_seq,
            'op_code': op_code,
            'item_id': item_id,
            'quantity': quantity,
            'balance': float(balance),
            'operator': operator,
            'note': note,
            'status_after': status_after,
        })
        self._save_movements()

    def add_item(self):
        print('\n--- เพิ่มรายการพัสดุ ---')
        item_id = self._prompt_int('รหัสพัสดุ (item_id): ', positive=True)
        if self._find_item_index(item_id) != -1:
            print('ผิดพลาด: รหัสพัสดุซ้ำ')
            return

        category_id = self._prompt_int('รหัสหมวดหมู่ (category_id): ', positive=True)
        if self._find_category_index(category_id) == -1:
            print('ผิดพลาด: ไม่พบหมวดหมู่ที่ระบุ')
            return

        name = self._prompt_text('ชื่อพัสดุ: ', max_bytes=32)
        unit = self._prompt_text('หน่วยนับ: ', max_bytes=16)
        location = self._prompt_text('สถานที่จัดเก็บ: ', max_bytes=12)
        quantity = self._prompt_int('จำนวนคงเหลือ: ', min_value=0)
        reorder_level = self._prompt_int('จุดสั่งซื้อขั้นต่ำ: ', min_value=0)
        unit_price = self._prompt_float('ราคาต่อหน่วย: ', min_value=0.0)

        free_index = -1
        for idx, item in enumerate(self.items):
            if item and item.get('status') == 0:
                free_index = idx
                break
        if free_index == -1:
            self.items.append({
                'item_id': item_id,
                'category_id': category_id,
                'name': name,
                'unit': unit,
                'location': location,
                'quantity': quantity,
                'reorder_level': reorder_level,
                'unit_price': float(unit_price),
                'status': 1,
            })
        else:
            self.items[free_index] = {
                'item_id': item_id,
                'category_id': category_id,
                'name': name,
                'unit': unit,
                'location': location,
                'quantity': quantity,
                'reorder_level': reorder_level,
                'unit_price': float(unit_price),
                'status': 1,
            }

        self._save_items()
        self._log_movement(1, item_id, quantity, quantity, 'ADMIN', 'ADD', 1)
        print(f'เพิ่มพัสดุ {name} สำเร็จ')

    def update_item(self):
        print('\n--- แก้ไขรายการพัสดุ ---')
        item_id = self._prompt_int('ระบุ item_id ที่ต้องการแก้ไข: ', positive=True)
        idx = self._find_item_index(item_id)
        if idx == -1:
            print('ไม่พบพัสดุที่ระบุ')
            return
        item = self.items[idx]
        if item.get('status') != 1:
            print('พัสดุนี้ถูกลบแล้ว ไม่สามารถแก้ไขได้')
            return

        print('เว้นว่างไว้เพื่อคงค่าเดิม')
        old_name = item['name']
        new_name = self._prompt_text(f'ชื่อพัสดุ [{old_name}]: ', max_bytes=32, allow_blank=True)
        if new_name:
            item['name'] = new_name

        old_category = item['category_id']
        new_category = self._prompt_int(f'รหัสหมวดหมู่ [{old_category}] (กด 0 เพื่อคงค่า): ', min_value=0, positive=False)
        if new_category > 0:
            if self._find_category_index(new_category) == -1:
                print('รหัสหมวดหมู่ไม่ถูกต้อง')
                return
            item['category_id'] = new_category

        old_unit = item['unit']
        new_unit = self._prompt_text(f'หน่วยนับ [{old_unit}]: ', max_bytes=16, allow_blank=True)
        if new_unit:
            item['unit'] = new_unit

        old_location = item['location']
        new_location = self._prompt_text(f'สถานที่จัดเก็บ [{old_location}]: ', max_bytes=12, allow_blank=True)
        if new_location:
            item['location'] = new_location

        old_reorder = item['reorder_level']
        new_reorder = self._prompt_int(f'จุดสั่งซื้อขั้นต่ำ [{old_reorder}] (กด -1 เพื่อคงค่า): ', min_value=-1, positive=False)
        if new_reorder >= 0:
            item['reorder_level'] = new_reorder

        old_price = item['unit_price']
        new_price = self._prompt_float(f'ราคาต่อหน่วย [{old_price}] (กด -1 เพื่อคงค่า): ', min_value=-1.0, positive=False)
        if new_price >= 0:
            item['unit_price'] = new_price

        self._save_items()
        self._log_movement(2, item_id, 0, item['quantity'], 'ADMIN', 'UPDATE', 1)
        print('อัปเดตข้อมูลสำเร็จ')

    def delete_item(self):
        print('\n--- ลบรายการพัสดุ (Logical Delete) ---')
        item_id = self._prompt_int('ระบุ item_id ที่ต้องการลบ: ', positive=True)
        idx = self._find_item_index(item_id)
        if idx == -1:
            print('ไม่พบพัสดุที่ระบุ')
            return
        item = self.items[idx]
        if item.get('status') == 0:
            print('พัสดุนี้ถูกลบแล้วแล้ว')
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

    def view_menu(self):
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

    def view_one(self):
        item_id = self._prompt_int('ระบุ item_id: ', positive=True)
        item = self._get_item_by_id(item_id)
        if item is None:
            print('ไม่พบข้อมูล')
            return
        self._print_item_row(item)

    def view_all(self):
        if not any(item and item.get('status') == 1 for item in self.items):
            print('ไม่มีข้อมูลพัสดุ Active')
            return
        print('\nรายการพัสดุทั้งหมด')
        print(f"{'ID':<8}{'หมวด':<12}{'ชื่อ':<20}{'จำนวน':>8}{'ขั้นต่ำ':>8}{'ราคา':>12}{'สถานะ':>8}")
        for item in self.items:
            if item and item.get('status') == 1:
                print(f"{item['item_id']:<8}{item['category_id']:<12}{item['name']:<20}{item['quantity']:>8}{item['reorder_level']:>8}{item['unit_price']:>12.2f}{'Active':>8}")

    def filter_items(self):
        print('1) ตามหมวดหมู่')
        print('2) ตามสถานะ')
        mode = input('เลือก: ').strip()
        if mode == '1':
            category_id = self._prompt_int('ระบุ category_id: ', positive=True)
            filtered = [item for item in self.items if item and item.get('category_id') == category_id]
        elif mode == '2':
            status = self._prompt_int('สถานะ (1=Active, 0=Deleted): ', min_value=0, max_value=1)
            filtered = [item for item in self.items if item and item.get('status') == status]
        else:
            print('ตัวเลือกไม่ถูกต้อง')
            return
        if not filtered:
            print('ไม่มีข้อมูลที่ตรงเงื่อนไข')
            return
        for item in filtered:
            self._print_item_row(item)

    def search_by_name(self):
        keyword = input('ค้นหาชื่อพัสดุ: ').strip()
        if not keyword:
            print('ต้องระบุคำค้นหา')
            return
        matches = [item for item in self.items if item and keyword.lower() in item.get('name', '').lower()]
        if not matches:
            print('ไม่พบข้อมูล')
            return
        for item in matches:
            self._print_item_row(item)

    def low_stock_items(self):
        low = [item for item in self.items if item and item.get('status') == 1 and item.get('quantity', 0) <= item.get('reorder_level', 0)]
        if not low:
            print('ไม่มีรายการใกล้หมด')
            return
        for item in low:
            self._print_item_row(item)

    def summary_stats(self):
        active = sum(1 for item in self.items if item and item.get('status') == 1)
        deleted = sum(1 for item in self.items if item and item.get('status') == 0)
        total_q = sum(item.get('quantity', 0) for item in self.items if item and item.get('status') == 1)
        total_value = sum(item.get('quantity', 0) * item.get('unit_price', 0.0) for item in self.items if item and item.get('status') == 1)
        low_count = sum(1 for item in self.items if item and item.get('status') == 1 and item.get('quantity', 0) <= item.get('reorder_level', 0))
        print('\nสถิติคลังพัสดุ')
        print(f'Active items: {active}')
        print(f'Deleted items: {deleted}')
        print(f'Total quantity: {total_q}')
        print(f'Total inventory value: {total_value:.2f} THB')
        print(f'Low-stock items: {low_count}')

    def stock_movement(self):
        print('\n--- Stock Movement ---')
        item_id = self._prompt_int('ระบุ item_id: ', positive=True)
        item = self._get_item_by_id(item_id)
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

        qty = self._prompt_int('จำนวน: ', min_value=1)
        if op == 'ISSUE' and qty > item['quantity']:
            print('ไม่สามารถเบิกเกินจำนวนคงเหลือ')
            return

        if op == 'RECEIVE':
            item['quantity'] += qty
            op_code = 4
            balance = item['quantity']
            note = 'RECEIVE'
            status_after = 1
        else:
            item['quantity'] -= qty
            op_code = 5
            balance = item['quantity']
            note = 'ISSUE'
            status_after = 1

        self._save_items()
        self._log_movement(op_code, item_id, qty, balance, 'ADMIN', note, status_after)
        print(f'ปรับยอดสำเร็จ: {item_id}, ยอดปัจจุบัน = {item["quantity"]}')

    def generate_report(self):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        active_items = [item for item in self.items if item and item.get('status') == 1]
        deleted_items = [item for item in self.items if item and item.get('status') == 0]
        total_value = sum(item['quantity'] * item['unit_price'] for item in active_items)
        low_items = [item for item in active_items if item['quantity'] <= item['reorder_level']]
        category_summary = {}
        for item in active_items:
            category_name = self._get_category_name(item['category_id'])
            category_summary[category_name] = category_summary.get(category_name, 0) + 1

        lines = []
        lines.append('Inventory Management System - Summary Report')
        lines.append(f'Generated At : {timestamp}')
        lines.append('App Version  : 1.0')
        lines.append('Endianness   : Little-Endian')
        lines.append('Encoding     : UTF-8 (fixed-length binary records)')
        lines.append('')
        lines.append('File Status')
        lines.append(f'- items.dat       : OK')
        lines.append(f'- categories.dat  : OK')
        lines.append(f'- movements.dat   : OK')
        lines.append('')
        lines.append('Record Summary')
        lines.append(f'- Item records (allocated) : {len(self.items)}')
        lines.append(f'- Active items             : {len(active_items)}')
        lines.append(f'- Deleted items            : {len(deleted_items)}')
        lines.append(f'- Free slots               : {len([x for x in self.items if x is None or (x and x.get("status") == 0)])}')
        lines.append(f'- Categories               : {len([x for x in self.categories if x and x.get("status") == 1])}')
        lines.append(f'- Movement records         : {len(self.movements)}')
        lines.append('')
        lines.append('Inventory Summary')
        lines.append(f'- Total quantity           : {sum(item["quantity"] for item in active_items)}')
        lines.append(f'- Total inventory value    : {total_value:,.2f} THB')
        lines.append(f'- Low-stock items          : {len(low_items)}')
        lines.append('')
        lines.append('Items by Category')
        for category_name, count in sorted(category_summary.items()):
            lines.append(f'- {category_name:<20} : {count}')
        if not category_summary:
            lines.append('- ไม่มีข้อมูลหมวดหมู่')
        lines.append('')
        lines.append('Latest Activities')
        for move in reversed(self.movements[-5:]):
            dt = datetime.fromtimestamp(move['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            lines.append(f'- [{dt}] {move["note"]} item={move["item_id"]} quantity={move["quantity"]}')
        self.report_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print(f'สร้างรายงานเรียบร้อยแล้ว: {self.report_path}')

    def _get_item_by_id(self, item_id: int):
        for item in self.items:
            if item and item.get('item_id') == item_id:
                return item
        return None

    def _get_category_name(self, category_id: int) -> str:
        for category in self.categories:
            if category and category.get('category_id') == category_id:
                return category.get('name', 'Unknown')
        return 'Unknown'

    def _print_item_row(self, item):
        print(f"ID={item['item_id']} | Category={item['category_id']} | Name={item['name']} | Qty={item['quantity']} | Reorder={item['reorder_level']} | Price={item['unit_price']:.2f} | Status={item['status']}")

    def _prompt_int(self, prompt: str, positive: bool = False, min_value: int = 0, max_value: int | None = None, allow_blank: bool = False, positive_false: bool = False):
        while True:
            value = input(prompt).strip()
            if not value:
                if allow_blank:
                    return min_value
                if positive_false:
                    return -1
                print('กรุณากรอกค่า')
                continue
            try:
                number = int(value)
            except ValueError:
                print('กรุณากรอกเป็นตัวเลขจำนวนเต็ม')
                continue
            if positive and number <= 0:
                print('ต้องเป็นจำนวนเต็มบวก')
                continue
            if number < min_value:
                print(f'ค่าต้องไม่น้อยกว่า {min_value}')
                continue
            if max_value is not None and number > max_value:
                print(f'ค่าต้องไม่เกิน {max_value}')
                continue
            return number

    def _prompt_float(self, prompt: str, min_value: float = 0.0, positive: bool = False):
        while True:
            value = input(prompt).strip()
            if not value:
                if positive:
                    print('กรุณากรอกค่า')
                    continue
                return min_value
            try:
                number = float(value)
            except ValueError:
                print('กรุณากรอกเป็นตัวเลขทศนิยม')
                continue
            if positive and number <= 0:
                print('ต้องเป็นค่ามากกว่า 0')
                continue
            if number < min_value:
                print(f'ค่าต้องไม่น้อยกว่า {min_value}')
                continue
            return number

    def _prompt_text(self, prompt: str, max_bytes: int, allow_blank: bool = False):
        while True:
            value = input(prompt).strip()
            if not value:
                if allow_blank:
                    return ''
                print('กรุณากรอกข้อความ')
                continue
            byte_len = len(value.encode('utf-8'))
            if byte_len > max_bytes:
                print(f'ข้อความยาวเกิน {max_bytes} bytes')
                continue
            return value

    def display_main_menu(self):
        print('\n===== ระบบคลังพัสดุและครุภัณฑ์ =====')
        print('1) Add Item')
        print('2) Update Item')
        print('3) Delete Item')
        print('4) View')
        print('5) Stock Movement')
        print('6) Generate Report')
        print('0) Exit')

    def run(self):
        while True:
            self.display_main_menu()
            choice = input('เลือกเมนู: ').strip()
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


def main():
    app = InventorySystem('.')
    app.run()


if __name__ == '__main__':
    main()
