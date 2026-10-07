# -*- coding: utf-8 -*-
import copy
import csv
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from nutrition_db import import_sr28, import_labels, get_food
from calculate_plan import calculate, deliver, grams
from review_logs import review

class NutritionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.db=self.root/'db.sqlite'
        labels=[{'id':'synthetic-v1','description':'Synthetic test food (not a recommendation)','brand':'TEST','sku':'TEST','evidence':'synthetic test evidence','accessed':'2026-10-07','license':'synthetic fixture','basis':'per100g','nutrients':{'kcal':100,'protein':10,'carbs':10,'fat':2,'fiber':0,'calcium':0,'iron':0,'sodium':0}}]
        self.labels=self.root/'labels.json'; self.labels.write_text(json.dumps(labels)); import_labels(self.labels,self.db)
        self.plan={'start_date':'2020-01-01','quantities_complete':True,'execution_reviewed':True,
         'foods':{'test':{'food_id':'label:synthetic-v1','match':'exact-label','match_evidence':'synthetic unit test only','weight_basis':'net raw','edible_yield':0.8,'yield_status':'verified','yield_evidence':'synthetic measured yield','inventory_storage':'synthetic freezer assumption','offer':{'pack_g':1000,'pack_price':10,'status':'verified','channel':'synthetic','sku':'TEST','evidence':'synthetic offer','checked':'2020-01-01','conditions':'synthetic pickup'}}},
         'days':[{'date':str(date(2020,1,1)+timedelta(days=i)),'meals':[{'type':k,'name':'test','steps':['synthetic'],'storage':'synthetic','ingredients':[{'food':'test','quantity':100,'unit':'g','weight_basis':'net raw'}]} for k in ('早餐','午餐','晚餐')]} for i in range(30)],
         'shopping':[{'purchase_date':'2020-01-01','start':'2020-01-01','end':'2020-01-30','prep':['synthetic only'],'delivery_cost':0,'delivery_status':'verified'}]}
    def tearDown(self):
        self.tmp.cleanup()
    def test_database_recomputes_not_supplied_totals(self):
        self.plan['days'][0]['meals'][0]['nutrition']={'kcal':9999}
        r=calculate(self.plan,self.db)
        self.assertEqual(r['days'][0]['nutrients']['kcal']['value'],300)
        self.assertFalse(r['gaps']); self.assertEqual(len(r['line_rows']),90)
        self.assertIn('synthetic test evidence',json.dumps(r['sources']))
    def test_yield_package_carryover(self):
        self.plan['shopping']=[dict(self.plan['shopping'][0],end='2020-01-15'),dict(self.plan['shopping'][0],purchase_date='2020-01-16',start='2020-01-16')]
        r=calculate(self.plan,self.db); a,b=r['shopping']
        self.assertEqual(a['packages'],6); self.assertEqual(a['stock_after_g'],375)
        self.assertEqual(b['packages'],6); self.assertEqual(b['stock_after_g'],750)
        self.assertEqual(r['estimated_purchase_total'],120)
    def test_unknown_nutrient_never_zero(self):
        c=sqlite3.connect(self.db); c.execute("delete from nutrients where name='calcium'"); c.commit(); c.close()
        n=calculate(self.plan,self.db)['days'][0]['nutrients']['calcium']
        self.assertIsNone(n['value']); self.assertEqual(n['missing_items'],3); self.assertEqual(n['known_subtotal'],0)
    def test_real_zero_preserved(self):
        self.assertEqual(calculate(self.plan,self.db)['days'][0]['nutrients']['fiber']['value'],0)
    def test_price_unknown_not_free(self):
        self.plan['foods']['test']['offer']['pack_price']=None
        r=calculate(self.plan,self.db); self.assertIsNone(r['estimated_purchase_total']); self.assertTrue(r['gaps'])
    def test_reference_blocks_verification(self):
        self.plan['foods']['test']['match']='reference'
        self.assertTrue(calculate(self.plan,self.db)['gaps'])
    def test_bad_basis(self):
        self.plan['days'][0]['meals'][0]['ingredients'][0]['weight_basis']='cooked'
        with self.assertRaises(ValueError): calculate(self.plan,self.db)
    def test_bad_date_or_missing_day(self):
        for p in (dict(self.plan,days=self.plan['days'][:-1]),copy.deepcopy(self.plan)):
            if len(p['days'])==30: p['days'][1]['date']='2020-01-01'
            with self.assertRaises(ValueError): calculate(p,self.db)
    def test_missing_meal(self):
        self.plan['days'][0]['meals'].pop()
        with self.assertRaises(ValueError): calculate(self.plan,self.db)
    def test_overlap_coverage(self):
        self.plan['shopping'].append(copy.deepcopy(self.plan['shopping'][0]))
        with self.assertRaises(ValueError): calculate(self.plan,self.db)
    def test_volume_requires_density_and_evidence(self):
        with self.assertRaises(ValueError): grams({'quantity':250,'unit':'ml'})
        self.assertEqual(grams({'quantity':250,'unit':'ml','density_g_ml':1.03,'conversion_evidence':'synthetic measurement'}),257.5)
    def test_nonfinite_and_boolean(self):
        for q in (True,float('nan'),float('inf'),0,-1):
            with self.assertRaises(ValueError): grams({'quantity':q,'unit':'g'})
    def test_unknown_food_id(self):
        self.plan['foods']['test']['food_id']='invented'
        with self.assertRaises(ValueError): calculate(self.plan,self.db)
    def test_output_complete_and_no_overwrite(self):
        r=calculate(self.plan,self.db); out=self.root/'out'; deliver(r,out)
        with (out/'每日营养.csv').open(encoding='utf-8-sig') as f:
            self.assertEqual(len(list(csv.DictReader(f))),30)
        md=(out/'30天饮食计划.md').read_text(); self.assertIn('2020-01-30',md)
        with self.assertRaises(ValueError): deliver(r,out)
    def test_csv_formula_protection(self):
        self.plan['days'][0]['meals'][0]['name']='=HYPERLINK("bad")'
        r=calculate(self.plan,self.db); deliver(r,self.root/'out')
        text=(self.root/'out/逐餐食材.csv').read_text(encoding='utf-8-sig')
        self.assertIn("'=HYPERLINK",text)
    def test_label_evidence_required_and_no_overwrite(self):
        with self.assertRaises(sqlite3.IntegrityError): import_labels(self.labels,self.db)
        x=json.loads(self.labels.read_text()); x[0]['id']='no-evidence'; x[0]['evidence']=''
        self.labels.write_text(json.dumps(x))
        with self.assertRaises(ValueError): import_labels(self.labels,self.db)
    def test_original_archive_missing_nutrient(self):
        z=self.root/'synthetic.zip'
        with zipfile.ZipFile(z,'w') as f:
            f.writestr('FOOD_DES.txt','~99999~^~0~^~Synthetic~\n')
            f.writestr('NUT_DATA.txt','~99999~^~208~^100\n')
        r=import_sr28(z,self.db,'2026-10-07'); c=sqlite3.connect(self.db)
        food=get_food(c,r['source_id']+':99999'); c.close()
        self.assertIsNone(food['nutrients']['fiber']); self.assertEqual(food['nutrients']['kcal'],100)
        import_sr28(z,self.db,'2026-10-07')
    def test_preparation_cannot_claim_different_food_amount(self):
        meal=self.plan['days'][0]['meals'][1]; meal['batch_id']='B1'
        portion={'id':'B1','prepare':'2020-01-01','eat':'2020-01-01','portions':1,
                 'inputs':copy.deepcopy(meal['ingredients']),'thaw':'fresh','storage':'synthetic'}
        self.plan['shopping'][0]['batches']=[portion]
        self.assertEqual(len(calculate(self.plan,self.db)['batch_rows']),1)
        portion['inputs'][0]['quantity']=200
        with self.assertRaises(ValueError): calculate(self.plan,self.db)
    def test_strict_cli_saves_draft_but_returns_failure(self):
        self.plan['foods']['test']['match']='reference'
        p=self.root/'plan.json'; p.write_text(json.dumps(self.plan))
        script=Path(__file__).resolve().parents[1]/'scripts/calculate_plan.py'
        proc=subprocess.run([sys.executable,str(script),'--db',str(self.db),'--plan',str(p),'--out',str(self.root/'strict'),'--strict'],capture_output=True,text=True)
        self.assertEqual(proc.returncode,1)
        self.assertTrue((self.root/'strict/核算与来源.json').exists())
    def test_general_database_cannot_be_exact_label(self):
        con=sqlite3.connect(self.db)
        data=json.loads(con.execute('select metadata from sources').fetchone()[0]); data['kind']='government-database'
        con.execute('update sources set metadata=?',(json.dumps(data),)); con.commit(); con.close()
        with self.assertRaises(ValueError): calculate(self.plan,self.db)
    def write_log(self,rows):
        p=self.root/'journal.csv'
        with p.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['date','morning_weight_kg','actual_kcal','intake_complete']); w.writeheader(); w.writerows(rows)
        return p
    def test_blank_records_not_observed(self):
        p=self.write_log([{'date':'2020-01-01'},{'date':'2020-01-25','morning_weight_kg':74}])
        r=review(p,'2020-01-01'); self.assertIsNone(r['observed_weight_change_kg']); self.assertEqual(r['complete_intake_days'],0)
    def test_trends_use_actual_and_complete_intake_only(self):
        rows=[{'date':str(date(2020,1,1)+timedelta(days=i)),'morning_weight_kg':v} for i,v in [(0,74),(1,74),(2,74),(23,75),(24,75),(25,75)]]
        rows[0].update(actual_kcal=2500,intake_complete='true'); rows[1].update(actual_kcal=100,intake_complete='false')
        r=review(self.write_log(rows),'2020-01-01'); self.assertEqual(r['observed_weight_change_kg'],1); self.assertEqual(r['mean_reported_complete_intake_kcal'],2500)
    def test_future_observations_rejected(self):
        future=str(date.today()+timedelta(days=1)); p=self.write_log([{'date':future,'morning_weight_kg':74}])
        with self.assertRaises(ValueError): review(p,future)

if __name__=='__main__': unittest.main()
