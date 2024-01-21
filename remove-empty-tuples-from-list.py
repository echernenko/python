lst1 = [( ), ('Paras', 5), ('Ankit', 11), ( ), ('Harsha', 115), ('Aditya', 115), ( ), ('Aditi', 3), ( )]
output = []

for tuple in lst1 :
    if (len(tuple) != 0) :
        output.append(tuple)

print(output)
