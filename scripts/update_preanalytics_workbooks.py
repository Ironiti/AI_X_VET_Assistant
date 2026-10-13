"""Patch only the four September records in server-owned Excel data files.

Uses the original OOXML package to retain all other sheets, formulas and caches.
Default is a dry run. --apply writes a same-filesystem backup before replacement.
"""
import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
import zipfile

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
FORM = 'Сопроводительное письмо от врача на бешенство'
PDF = 'БЕШЕНСТВО_Преаналитические_требования_к_тесту_AN239RAB_и_AN239RABCT'
UPDATES = {
    'AN116': {'patient_preparation': 'Специальной подготовки не требуется'},
    'AN239RAB': {'form_name': FORM, 'form_link': '', 'additional_information_name': PDF},
    'AN239RABCT': {'form_name': FORM, 'form_link': '', 'additional_information_name': PDF},
}


def patch_workbook(path, apply=False):
    path = Path(path)
    before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    with zipfile.ZipFile(path) as source:
        shared = []
        if 'xl/sharedStrings.xml' in source.namelist():
            shared = [''.join(node.itertext()) for node in ET.fromstring(source.read('xl/sharedStrings.xml'))]
        raw = source.read('xl/worksheets/sheet1.xml')
        for _, (prefix, uri) in ET.iterparse(io.BytesIO(raw), events=['start-ns']):
            if not prefix.startswith('ns'):
                ET.register_namespace(prefix, uri)
        tree = ET.fromstring(raw)
        rows = tree.find(NS + 'sheetData')

        def value(cell):
            if cell is None:
                return ''
            if cell.get('t') == 'inlineStr':
                inline = cell.find(NS + 'is')
                return ''.join(inline.itertext()) if inline is not None else ''
            v = cell.findtext(NS + 'v', '')
            return shared[int(v)] if cell.get('t') == 's' and v else v

        headers = {value(cell): ''.join(c for c in cell.get('r') if c.isalpha()) for cell in rows[0]}
        required = {'test_code', 'patient_preparation', 'form_name', 'additional_information_name'}
        if not required <= headers.keys():
            raise ValueError(f'Unexpected columns: {path}')
        found = set()
        changes = []
        all_codes = []
        for row in rows[1:]:
            cells = {''.join(c for c in cell.get('r') if c.isalpha()): cell for cell in row}
            code = value(cells.get(headers['test_code'])).strip()
            if code:
                all_codes.append(code)
            if code == 'AN371КР':
                changes.append({'code': code, 'action': 'delete'})
                for cell in row:
                    for child in list(cell):
                        if child.tag in (NS+'v', NS+'f', NS+'is'):
                            cell.remove(child)
                    cell.attrib.pop('t', None)
            elif code in UPDATES:
                found.add(code)
                for field, new in UPDATES[code].items():
                    if field not in headers:
                        continue
                    cell = cells.get(headers[field])
                    old = value(cell)
                    if old == new:
                        continue
                    changes.append({'code': code, 'field': field, 'before': old, 'after': new})
                    if cell is None:
                        cell = ET.SubElement(row, NS+'c', {'r': headers[field]+row.get('r')})
                    for child in list(cell):
                        if child.tag in (NS+'v', NS+'f', NS+'is'):
                            cell.remove(child)
                    cell.attrib.pop('t', None)
                    if new:
                        cell.set('t', 'inlineStr')
                        ET.SubElement(ET.SubElement(cell, NS+'is'), NS+'t').text = new
        if set(UPDATES) != found:
            raise ValueError(f'Missing required tests: {set(UPDATES)-found} in {path}')
        for code in UPDATES:
            if all_codes.count(code) != 1:
                raise ValueError(f'Duplicate test: {code} in {path}')
        result = {'path': str(path), 'sha256_before': before_hash, 'records_before': len(all_codes), 'changes': changes}
        if not apply or not changes:
            return result
        backup = path.parents[1] / 'backups' / ('preanalytics_202609_' + before_hash + '.xlsx')
        backup.parent.mkdir(exist_ok=True)
        if not backup.exists():
            os.link(path, backup)
        fd, temporary = tempfile.mkstemp(prefix='.preanalytics-', suffix='.xlsx', dir=path.parent)
        os.close(fd)
        try:
            with zipfile.ZipFile(temporary, 'w') as dest:
                for part in source.infolist():
                    dest.writestr(copy.copy(part), ET.tostring(tree, encoding='utf-8', xml_declaration=True)
                        if part.filename == 'xl/worksheets/sheet1.xml' else source.read(part.filename))
            with zipfile.ZipFile(temporary) as dest:
                assert dest.namelist() == source.namelist()
                assert all(dest.read(name) == source.read(name) for name in source.namelist()
                           if name != 'xl/worksheets/sheet1.xml')
            # Refuse to overwrite an input modified since planning.
            assert hashlib.sha256(path.read_bytes()).hexdigest() == before_hash
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        result['backup'] = str(backup)
        result['sha256_after'] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    paths = [args.repo/'data/processed'/name for name in ('data_with_abbreviations_new.xlsx', 'joined_data.xlsx')]
    plans = [patch_workbook(path) for path in paths]
    if args.apply:
        plans = [patch_workbook(path, True) for path in paths]
        assert all(not patch_workbook(path)['changes'] for path in paths)
    print(json.dumps(plans, ensure_ascii=False, indent=2))
