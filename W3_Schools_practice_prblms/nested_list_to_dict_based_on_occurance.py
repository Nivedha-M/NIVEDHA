lsts=[[1, 2, 3, 2], [4, 5, 6, 2], [7, 8, 9, 5]]

d=[item for lst in lsts for item in lst]
print(d)

ele_occurance={ele:d.count(ele) for ele in d}
print(ele_occurance)

#***************************************ONE LINE CODE****************************************************
one_line={item:lst.count(item) for lst in lsts for item in lst}
print(f"one_line:{one_line}")