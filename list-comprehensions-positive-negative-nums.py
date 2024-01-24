lst = [1, 2, 5, -11, -9, 10, 13, 15, -17, -19, -21, -23, 25, 27, -29]

pos_nums = [n for n in lst if n >= 0]
neg_nums = [n for n in lst if n < 0]

print(pos_nums)
print(neg_nums)
