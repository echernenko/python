print('splitting to char - cheating')
num = input('enter a number:  ')
output = '';
for char in num:
    output = char + output;

print('Original number =', num)
print('Reversed number = ', output)
if int(num) == int(output) :
  print('Original and reversed numbers are same')
else :
  print('Original and reversed numbers are different')

print('real math - no cheating')
num = int(input('enter a number: '))
print(num)
orinum = num
revnum = 0
while(num > 0) :
  rem = num % 10
  revnum = (revnum * 10) + rem
  num = num // 10

print('Original number =', orinum)
print('Reversed number = ', revnum)
if orinum == revnum :
  print('Original and reversed numbers are same')
else :
  print('Original and reversed numbers are different')
