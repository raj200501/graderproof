from decimal import Decimal	

TAX_RATE = Decimal("0.20")   
  
def gross(net):
    """Return the price including tax."""	 
    return (net * (1 + TAX_RATE)).quantize(Decimal("0.01"))


def discount(price, percent):    
	return price * (100 - percent) / 100	
