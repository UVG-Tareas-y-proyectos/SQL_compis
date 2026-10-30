"""Catálogo JSON, registros CSV y directorios propios. No utiliza un DBMS."""

import base64
from copy import deepcopy
import csv
import io
import json
import os
from pathlib import Path
import tempfile
import threading

from .model import SQLError
from .types import convert

LOCKS = {}


def encode_json(value):
    return json.dumps(value, ensure_ascii=False, default=str, indent=2).encode('utf-8')


class FileStorage:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = LOCKS.setdefault(str(self.root), threading.RLock())
        self.recover()
        self.reload()

    def reload(self):
        try:
            file = self.root / 'metadata.json'
            self.metadata = json.loads(file.read_text(encoding='utf-8')) if file.exists() else {
                'version': 1, 'tables': {}, 'indexes': {}}
        except (OSError, ValueError) as exc:
            raise SQLError(f'no se pudo leer el catálogo: {exc}', phase='almacenamiento') from exc

    def path(self, relative):
        target = (self.root / relative).resolve()
        if self.root not in target.parents:
            raise SQLError('ruta de almacenamiento fuera de la base', phase='almacenamiento')
        return target

    def atomic_write(self, relative, data):
        target = self.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        try:
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def recover(self):
        journal = self.root / 'journal.json'
        if not journal.exists():
            return
        try:
            for name, encoded in json.loads(journal.read_text(encoding='utf-8')).items():
                if encoded is None:
                    self.path(name).unlink(missing_ok=True)
                else:
                    self.atomic_write(name, base64.b64decode(encoded))
            journal.unlink()
        except (OSError, ValueError) as exc:
            raise SQLError(f'no se pudo recuperar la escritura interrumpida: {exc}', phase='almacenamiento') from exc

    def commit(self, metadata, updates=None):
        updates = dict(updates or {})
        updates['metadata.json'] = encode_json(metadata)
        before = {name: base64.b64encode(self.path(name).read_bytes()).decode('ascii')
                  if self.path(name).exists() else None for name in updates}
        self.atomic_write('journal.json', encode_json(before))
        try:
            for name, data in updates.items():
                if data is None:
                    self.path(name).unlink(missing_ok=True)
                else:
                    self.atomic_write(name, data)
            (self.root / 'journal.json').unlink()
            self.metadata = deepcopy(metadata)
        except OSError as exc:
            self.recover()
            self.reload()
            raise SQLError(f'escritura cancelada: {exc}', phase='almacenamiento') from exc

    def table_files(self, name, schema, rows):
        columns = [c['name'] for c in schema['columns']]
        buffer = io.StringIO(newline='')
        writer = csv.writer(buffer, lineterminator='\n')
        writer.writerow(['__rid', *columns])
        content = bytearray(buffer.getvalue().encode('utf-8'))
        offsets = {}
        for row in rows:
            buffer.seek(0)
            buffer.truncate(0)
            writer.writerow([row['__rid'], *[json.dumps(row[c], ensure_ascii=False, default=str) for c in columns]])
            offsets[str(row['__rid'])] = len(content)
            content.extend(buffer.getvalue().encode('utf-8'))
        return {f'tables/{name}.csv': bytes(content), f'offsets/{name}.json': encode_json(offsets)}

    def rows(self, name, ids=None):
        schema = self.metadata['tables'][name]
        columns = schema['columns']
        path = self.path(f'tables/{name}.csv')
        try:
            if ids is None:
                with path.open(encoding='utf-8', newline='') as file:
                    reader = csv.reader(file)
                    next(reader)
                    records = list(reader)
            else:
                offsets = json.loads(self.path(f'offsets/{name}.json').read_text(encoding='utf-8'))
                records = []
                with path.open('rb') as file:
                    for rid in sorted(ids):
                        if str(rid) not in offsets:
                            continue
                        file.seek(offsets[str(rid)])
                        records.append(next(csv.reader([file.readline().decode('utf-8')])))
            output = []
            for record in records:
                if len(record) != len(columns)+1:
                    raise ValueError('registro CSV con longitud incorrecta')
                row = {'__rid': int(record[0])}
                for column, cell in zip(columns, record[1:]):
                    row[column['name']] = convert(json.loads(cell), column)
                output.append(row)
            return output
        except (OSError, ValueError, StopIteration, SQLError) as exc:
            raise SQLError(f"no se pudo leer la tabla '{name}': {exc}", phase='almacenamiento') from exc

    def save_rows(self, name, rows, metadata=None, extra=None):
        metadata = deepcopy(metadata or self.metadata)
        metadata['tables'][name]['count'] = len(rows)
        updates = self.table_files(name, metadata['tables'][name], rows)
        updates.update(extra or {})
        self.commit(metadata, updates)
