# -*- coding: utf-8 -*-
"""Local, provenance-preserving SQLite nutrition registry. Python stdlib only."""
import argparse
import hashlib
import json
import math
import sqlite3
import zipfile
from datetime import date
from pathlib import Path

KEYS = {'kcal': ('208', 'kcal'), 'protein': ('203', 'g'), 'carbs': ('205', 'g'),
        'fat': ('204', 'g'), 'fiber': ('291', 'g'), 'calcium': ('301', 'mg'),
        'iron': ('303', 'mg'), 'sodium': ('307', 'mg')}
URL = 'https://www.ars.usda.gov/ARSUserFiles/80400525/Data/SR/SR28/dnload/sr28asc.zip'

def positive(value, field, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        raise ValueError(field + ': invalid numeric value')
    return value

def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute('PRAGMA foreign_keys=ON')
    con.executescript('''
    CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, metadata TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS foods(id TEXT PRIMARY KEY, description TEXT NOT NULL,
      source_id TEXT NOT NULL REFERENCES sources(id), basis TEXT NOT NULL, metadata TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS nutrients(food_id TEXT REFERENCES foods(id), name TEXT,
      value REAL NOT NULL CHECK(value>=0), unit TEXT NOT NULL, PRIMARY KEY(food_id,name));
    ''')
    return con

def import_sr28(archive, db, accessed):
    date.fromisoformat(accessed)
    digest = hashlib.sha256(Path(archive).read_bytes()).hexdigest()
    sid = 'usda-sr28:' + digest
    con = connect(db)
    strip = lambda v: v.strip('~')
    with zipfile.ZipFile(archive) as z:
        descriptions = {strip(r[0]): strip(r[2]) for r in
                        (line.split('^') for line in z.read('FOOD_DES.txt').decode('latin1').splitlines())}
        values = {}
        reverse = {v[0]: (k, v[1]) for k, v in KEYS.items()}
        for line in z.read('NUT_DATA.txt').decode('latin1').splitlines():
            r = line.split('^')
            if strip(r[1]) in reverse:
                name, unit = reverse[strip(r[1])]
                value = positive(float(r[2]), name, True)
                values.setdefault(strip(r[0]), []).append((name, value, unit))
    metadata = dict(kind='government-database', publisher='USDA', version='SR28 2015/2016',
                    url=URL, accessed=accessed, sha256=digest, license='US public-domain government data',
                    caveat='Historical US composition reference; not Chinese SKU labels; archive hash identifies bytes, not authenticity certification')
    with con:
        con.execute('INSERT OR IGNORE INTO sources VALUES (?,?)', (sid, json.dumps(metadata)))
        for ndb, desc in descriptions.items():
            fid = sid + ':' + ndb
            con.execute('INSERT OR IGNORE INTO foods VALUES (?,?,?,?,?)',
                        (fid, desc, sid, 'per100g', json.dumps({'ndb_id': ndb, 'state': 'see description'})))
            con.executemany('INSERT OR IGNORE INTO nutrients VALUES (?,?,?,?)',
                            [(fid, k, v, u) for k, v, u in values.get(ndb, [])])
    con.close()
    return {'source_id': sid, 'foods': len(descriptions), 'sha256': digest}

def import_labels(file, db):
    labels = json.loads(Path(file).read_text(encoding='utf-8'))
    con = connect(db)
    with con:
        for item in labels:
            for key in ('id', 'description', 'brand', 'sku', 'evidence', 'accessed', 'license'):
                if not isinstance(item.get(key), str) or not item[key].strip():
                    raise ValueError('label missing ' + key)
            date.fromisoformat(item['accessed'])
            if item.get('basis') != 'per100g':
                raise ValueError('label must be normalized per100g with conversion evidence')
            sid = 'label:' + item['id']
            # Reject replacing an existing evidence record; use a new versioned ID.
            con.execute('INSERT INTO sources VALUES (?,?)', (sid, json.dumps(item, ensure_ascii=False)))
            con.execute('INSERT INTO foods VALUES (?,?,?,?,?)',
                        (sid, item['description'], sid, 'per100g', json.dumps({'brand': item['brand'], 'sku': item['sku']})))
            for k, v in item['nutrients'].items():
                if k not in KEYS:
                    raise ValueError('unsupported nutrient ' + k)
                if v is not None:
                    positive(v, k, True)
                    con.execute('INSERT INTO nutrients VALUES (?,?,?,?)', (sid, k, v, KEYS[k][1]))
    con.close()
    return {'labels': len(labels)}

def get_food(con, fid):
    row = con.execute('SELECT description,source_id,basis,metadata FROM foods WHERE id=?', (fid,)).fetchone()
    if not row:
        raise ValueError('unknown food_id: ' + fid)
    source = con.execute('SELECT metadata FROM sources WHERE id=?', (row[1],)).fetchone()
    nutrients = {k: None for k in KEYS}
    for k, v, u in con.execute('SELECT name,value,unit FROM nutrients WHERE food_id=?', (fid,)):
        if k not in KEYS or u != KEYS[k][1]:
            raise ValueError('invalid nutrient unit')
        nutrients[k] = positive(v, k, True)
    return dict(id=fid, description=row[0], source_id=row[1], basis=row[2],
                metadata=json.loads(row[3]), source=json.loads(source[0]), nutrients=nutrients)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    imp = sub.add_parser('import-sr28'); imp.add_argument('--archive', required=True); imp.add_argument('--accessed', required=True); imp.add_argument('--db', required=True)
    lab = sub.add_parser('import-labels'); lab.add_argument('--file', required=True); lab.add_argument('--db', required=True)
    search = sub.add_parser('search'); search.add_argument('--db', required=True); search.add_argument('--query', required=True)
    a = p.parse_args()
    if a.command == 'import-sr28':
        result = import_sr28(a.archive, a.db, a.accessed)
    elif a.command == 'import-labels':
        result = import_labels(a.file, a.db)
    else:
        con = sqlite3.connect('file:' + str(Path(a.db).resolve()) + '?mode=ro', uri=True)
        result = [{'id': r[0], 'description': r[1]} for r in con.execute('SELECT id,description FROM foods WHERE description LIKE ? ORDER BY id LIMIT 30', ('%' + a.query + '%',))]
        con.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
