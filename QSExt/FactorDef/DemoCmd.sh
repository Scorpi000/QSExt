python .\updateFactorData.py .\stock_cn_factor_momentum.py -tdb HDB -slb 3 -iddb LDB:stock_cn_day_bar_nafilled

python .\updateFactorData.py .\stock_cn_factor_momentum.py -sdt 2019-04-15 -edt 2019-04-30 -sdb LDB:HDF5DB -scfg .\QSConfig\HDF5DBConfig.json -dtdb LDB:stock_cn_day_bar_nafilled -iddb LDB:stock_cn_day_bar_nafilled

python .\updateFactorData.py .\stock_cn_multi_factor_classic.py -sdt 2019-04-15 -edt 2019-04-30 -dtdb LDB:stock_cn_day_bar_nafilled -iddb LDB:stock_cn_day_bar_nafilled -darg {'factor_info_file':'./conf/stock_cn_multi_factor_classic.csv'}