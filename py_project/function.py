def birth_year(age, current_year):
  birth_y = current_year - age
  return birth_y

curr_year = input("Enter current year: ")
age = input("Enter your age: ")
birth_year = int(curr_year) - int(age)

print("Looks like you were born in: %s" % birth_year)
