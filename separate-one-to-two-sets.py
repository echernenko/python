st = {'Amelia', 'Ava', 'Alexander', 'Avery', 'Asher', 'Bam', 'Bob', 'Bali', 'Bela', 'Boni'}

a_set = set()
b_set = set()

for el in st:
  if (el.startswith('A')):
    a_set.add(el)
  else:
    b_set.add(el)

print(a_set)
print(b_set)

# print(tuple(sorted(a_set)))
# print(tuple(sorted(b_set)))
