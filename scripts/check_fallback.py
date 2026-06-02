import pickle, os

with open('D:\\workSpace\\amv-rqalpha-backtest\\bundle\\bundle\\instruments.pk', 'rb') as f:
    instruments = pickle.load(f)

codes = ['510050.XSHG', '510300.XSHG', '510500.XSHG', '159919.XSHE', '159915.XSHE', '159901.XSHE', '510880.XSHG', '510180.XSHG', '159949.XSHE']
for inst in instruments:
    if isinstance(inst, dict) and inst.get('order_book_id') in codes:
        oid = inst['order_book_id']
        print(f"{oid}: {inst.get('symbol','')} listed={inst.get('listed_date','')}")
