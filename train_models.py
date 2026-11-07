"""Time-split calibrated RF plus genuine-only sklearn autoencoder."""
import joblib, numpy as np, pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import RobustScaler
from sklearn.neural_network import MLPRegressor
from config import DATA_PATH, MODEL_DIR, FEATURE_COLUMNS, RANDOM_SEED
from dataset_features import dataframe_features, ae_input

def main():
 d=pd.read_csv(DATA_PATH).sort_values('timestamp');cut=int(len(d)*.8);train=d.iloc[:cut];X=dataframe_features(d);y=d.is_fraud.astype(int)
 # Last 15% of train remains validation-only for thresholds; test untouched.
 val_start=int(len(train)*.85);xtr=X.iloc[:val_start];ytr=y.iloc[:val_start]
 rf=CalibratedClassifierCV(RandomForestClassifier(n_estimators=180,max_depth=18,min_samples_leaf=2,class_weight='balanced',n_jobs=-1,random_state=RANDOM_SEED),cv=3,method='sigmoid').fit(xtr,ytr)
 atr=ae_input(xtr);scaler=RobustScaler().fit(atr);genuine=scaler.transform(atr[ytr==0]);ae=MLPRegressor(hidden_layer_sizes=(24,8,24),max_iter=200,random_state=RANDOM_SEED,early_stopping=True).fit(genuine,genuine)
 err=np.mean((ae.predict(scaler.transform(atr))-scaler.transform(atr))**2,axis=1);lo,hi=np.percentile(err,[1,99])
 MODEL_DIR.mkdir(parents=True,exist_ok=True);joblib.dump({'model':rf,'scaler':scaler,'autoencoder':ae,'anom_lo':float(lo),'anom_hi':float(hi),'features':FEATURE_COLUMNS,'ae_log':True},MODEL_DIR/'fraud_model.joblib')
 print(f'Trained on {len(xtr):,} rows; validation slice {len(train)-val_start:,}; held-out test {len(d)-cut:,}.')
if __name__=='__main__':main()
