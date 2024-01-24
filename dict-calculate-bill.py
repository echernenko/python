prices = { 'Bottles' : 30, 'Tiffin' : 100, 'Bag' : 400, 'Bicycle' : 2000 }
stock = { 'Bottles' : 10 , 'Tiffin' : 8, 'Bag' : 1, 'Bicycle' : 5}
total_amount = 0;
for key, value in prices.items():
  curr_amount = value * stock[key];
  total_amount += curr_amount
  print(key, curr_amount)
print('Total Bill Amount =', total_amount)
