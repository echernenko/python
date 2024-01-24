s = "James BOnd"

def count_lower_upper(s) :
  upper_count = 0;
  lower_count = 0
  for char in s:
    if char.isupper():
      upper_count += 1
      continue
    if char.islower():
      lower_count += 1
      continue
  return {'Lower': lower_count, 'Upper': upper_count}

print(count_lower_upper(s))
