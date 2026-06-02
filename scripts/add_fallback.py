# 把兜底ETF也加入concept_etf_map.csv，方便select_etf_for_date映射
import pandas as pd

mapping = pd.read_csv('D:\\workSpace\\amv-rqalpha-backtest\\data\\concept_etf_map.csv')

# 检查是否已有宽基ETF
has_broad = mapping[mapping['concept'] == '宽基指数']
if has_broad.empty:
    fallbacks = pd.DataFrame([
        ("宽基指数", "510050.XSHG", "华夏上证50ETF", 0),
        ("宽基指数", "159901.XSHE", "易方达深证100ETF", 1),
        ("宽基指数", "510880.XSHG", "华泰柏瑞上证红利ETF", 2),
        ("宽基指数", "159915.XSHE", "易方达创业板ETF", 3),
        ("宽基指数", "510300.XSHG", "华泰柏瑞沪深300ETF", 4),
        ("宽基指数", "510500.XSHG", "南方中证500ETF", 5),
    ], columns=['concept', 'order_book_id', 'etf_name', 'priority'])
    mapping = pd.concat([mapping, fallbacks], ignore_index=True)
    mapping.to_csv('D:\\workSpace\\amv-rqalpha-backtest\\data\\concept_etf_map.csv', index=False)
    print(f'Added {len(fallbacks)} fallback ETFs')
else:
    print('Fallback ETFs already exist')
print(f'Total rows: {len(mapping)}')
print(mapping[mapping['concept'] == '宽基指数'].to_string())
