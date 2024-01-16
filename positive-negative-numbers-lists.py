lst1 = [1, -9, -6, -45, -78, -1, 2, 3, 4, 5]
pos_lst1 = []
neg_lst1 = []

for num in lst1 :
    if num > 0 :
        pos_lst1.append(num)
    else :
        neg_lst1.append(num)

print('Original list =', lst1)
print('Positive numbers list =', pos_lst1)
print('Negative numbers list =', neg_lst1)
