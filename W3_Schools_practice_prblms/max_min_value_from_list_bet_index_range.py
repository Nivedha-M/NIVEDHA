lst=[4, 3, 0, 5, 3, 0, 2, 3, 4, 2, 4, 3, 5]
start_index=3
last_index=8
new=[]
while(start_index<=last_index):
    print(f"start_index:{start_index}")
    new.append(lst[start_index])
    start_index+=1
print(new)
max_min=(max(new),min(new))
print(max_min)


