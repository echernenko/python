# approach #1 - using temp variables

s = 'Razmattaz'
lst = ['R', 'a', 'a', 'z', 'm', 'a', 't', 't', 'a', 'z']
tpl = ('R', 'a', 'a', 'z', 'm', 'a', 't', 't', 'a', 'z')

# using temporary set to remove
# all duplicate elements present in a string, list, and tuple
tmp_set = set()

# string subtask
tmp_str = ''
for char in s :
  if (char not in tmp_set) :
    tmp_str += char
  tmp_set.add(char)
# clearing set
tmp_set.clear()
# changing s
s = tmp_str

# list subtask
tmp_lst = []
for el in lst:
  if (el not in tmp_set):
    tmp_lst.append(el)
  tmp_set.add(el)
# clearing set
tmp_set.clear()
lst = tmp_lst

# tuple subtask
tpl = tuple(lst)

# output
print(s)
print(lst)
print(tpl)



# approach #2 - using sorted
s = 'Razmattaz'
lst = ['R', 'a', 'a', 'z', 'm', 'a', 't', 't', 'a', 'z']
tpl = ('R', 'a', 'a', 'z', 'm', 'a', 't', 't', 'a', 'z')

s = ''.join(sorted(set(s), key = s.index))
print(s)

lst = ['R', 'a', 'a', 'z', 'm', 'a', 't', 't', 'a', 'z']
lst = list(sorted(set(lst), key = s.index))
print(lst)

tpl = ('R', 'a', 'a', 'z', 'm', 'a', 't', 't', 'a', 'z')
tpl = tuple(sorted(set(tpl), key = s.index))
print(tpl)
