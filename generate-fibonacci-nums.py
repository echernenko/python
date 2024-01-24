lst = [0, 1]
[lst.append(lst[n-1] + lst[n-2]) for n in range(2, 20)]

print('First 20 Fibonacci numbers:', lst)
