#165. Write a Python program to split a given list into specified sized chunks.

lst = [12, 45, 23, 67, 78, 90, 45, 32, 100, 76, 38, 62, 73, 29, 83]
size = 6
print(list(lst[ele:ele+size]for ele in range(0,len(lst),size)))

#======================================================================================================================================

lst = [12, 45, 23, 67, 78, 90, 45, 32, 100, 76, 38, 62, 73, 29, 83]
size = 3
new = []
for ele in range(0, len(lst), size):
    pass