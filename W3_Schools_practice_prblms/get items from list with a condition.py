#164. Write a Python program to get the items from a given list with specific condition.

#my logic
lst=[12, 45, 23, 67, 78, 90, 45, 32, 100, 76, 38, 62, 73, 29, 83]
s=45
count=0
for ele in lst:
    if ele>s and ele%2==0:
        count+=1
print(f"count:{count}")

#====================*********************************************==================
lst=[12, 45, 23, 67, 78, 90, 45, 32, 100, 76, 38, 62, 73, 29, 83]
s=45
print(sum(1 for ele in lst if (ele>s and ele%2==0)))


