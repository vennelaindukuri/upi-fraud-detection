"""Pick thresholds for target recall with a compact grid search on validation data."""
import numpy as np
from sklearn.metrics import recall_score
from config import ALLOW_THRESHOLD, BLOCK_THRESHOLD
def tune(risk, truth, target_recall=.90):
    """Returns (allow, block); OTP resolves genuine/fraud ground truth in validation."""
    best=(ALLOW_THRESHOLD,BLOCK_THRESHOLD)
    for allow in np.arange(.15,.46,.05):
        for block in np.arange(.55,.91,.05):
            result=np.where(risk>block,1,np.where(risk>=allow,truth,0))
            if recall_score(truth,result)>=target_recall: best=(round(allow,2),round(block,2))
    return best
