
import importlib,sys
pkgs=["pandas","numpy","ccxt","matplotlib","seaborn","yaml"]
for p in pkgs:
  try:
    importlib.import_module(p)
  except Exception as e:
    print(p,"ERROR",e); sys.exit(1)
print("imports ok")