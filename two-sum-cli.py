import sys

nums = [1,3,4,5,7]
target = 9

# print(len(sys.argv))

if (len(sys.argv) > 1):
  nums = list(map(int, sys.argv[1].split(',')))
  target = sys.argv[2]

for i in range(len(nums)):
  for j in range(i+1, len(nums)):
    if ((nums[i] + nums[j]) == int(target)):
      print("match found: ", [i, j], "in array: ", nums, " with the target set: ", target)
      exit();

print("match was not found");
