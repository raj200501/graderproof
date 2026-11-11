import sys

from app.pricing import gross  


def main(argv):  
    for arg in argv[1:]:
        print(gross(arg)) 
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))  