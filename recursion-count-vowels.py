s = "Raindrops on roses"
idx = 0
count = 0
vowels = ['a','e','i','o','u','A','E','I','O','U']

# loop
def count_vowels(s):
  count = 0
  for char in s:
    if char in vowels:
      count += 1
  return count

# res = count_vowels(s)
# print(res)

# recursion
def count_vowels(s, idx, count):
  # exit condition
  if idx == len(s):
    return count
  else:
    if s[idx] in vowels:
      count += 1
    return count_vowels(s, idx+1, count)

res = count_vowels(s, idx, count)
print(res)
