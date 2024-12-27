# Write a Python program to get the index of the first element which is greater than a specified element

#MY LOGIC
lst = [12, 45, 23, 67, 78, 90, 100, 76, 38, 62, 73, 29, 83]
sec = 55
for ele in lst:
    if ele > sec:
        print(f"{lst.index(ele)},")
        break

#=======================================================================================
lst = [12, 45, 23, 67, 78, 90, 100, 76, 38, 62, 73, 29, 83]
s= 55
print(next(ele[0] for ele in enumerate(lst) if ele[1] > s))
# print(f"hi:{hi}")


