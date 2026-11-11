import sys

sys.path.insert(0, ".")
from classify import classify

ok = classify(3) == "fizz" and classify(5) == "buzz" and classify(15) == "fizzbuzz"
sys.exit(0 if ok else 1)
