total = int(input('How many numbers do you wish to input: '))
numbers = [float(num) for num in input('Enter all numbers: ').split()]
avg = 0.0;
for num in numbers :
    avg += num
avg = avg / total;
print('Average of', total, 'numbers is:', avg)
