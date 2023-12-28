s = "The Terrible Tiger Tore The Towel"
modifiedString = '';
a = 'T'
b = 't'
# print(len(s))
for i in range(0, len(s)):
    currSymbol = s[i]
    if (currSymbol == a):
        currSymbol = b;
        print(i)
    modifiedString += currSymbol
print(modifiedString)
