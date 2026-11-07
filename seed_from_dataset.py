"""Load the supplied fictional @okshield CSV ecosystem into SQLite; safe to rerun."""
import pandas as pd
from config import DATA_PATH
from db import connect, reset_demo_tables

DATA = DATA_PATH.parent
def main():
    reset_demo_tables()
    users=pd.read_csv(DATA/'users.csv'); receivers=pd.read_csv(DATA/'receivers.csv'); tx=pd.read_csv(DATA/'transactions.csv')
    users=users.rename(columns={'user_id':'upi_id','primary_device':'usual_device'})[['upi_id','name','role','typical_amount','usual_device']]
    receivers=receivers.rename(columns={'receiver_id':'upi_id','receiver_name':'name'})
    receivers['category']=receivers['receiver_type']
    receivers['is_flagged']=(receivers['category'].isin(['suspicious','mule'])).astype(int);receivers['qr_name']=receivers['name']
    with connect() as con:
        users.to_sql('users',con,if_exists='append',index=False)
        receivers[['upi_id','name','category','account_age_days','receiver_risk_score','is_flagged','qr_name']].to_sql('receivers',con,if_exists='append',index=False)
        # Preserve all dataset columns used by live/evaluation code in a side table.
        tx.to_sql('dataset_transactions',con,if_exists='replace',index=False)
        base=tx.rename(columns={'sender_id':'sender_id','receiver_id':'receiver_id'})
        base['location']='Dataset';base['decision']='ALLOW';base['risk_score']=0.;base['latency_ms']=0.
        base[['txn_id','sender_id','receiver_id','amount','timestamp','hour','device_id','is_new_receiver','is_fraud','location','decision','risk_score','latency_ms']].to_sql('transactions',con,if_exists='append',index=False)
        con.execute('CREATE INDEX IF NOT EXISTS idx_dataset_sender_time ON dataset_transactions(sender_id,timestamp)')
    print(f'Loaded {len(users):,} users, {len(receivers):,} receivers and {len(tx):,} transactions.')
if __name__=='__main__': main()
