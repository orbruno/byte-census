import os, sys, time
from concurrent.futures import ThreadPoolExecutor
def walk(root):
    total=n=0; seen=set(); stack=[root]
    while stack:
        d=stack.pop()
        try: it=os.scandir(d)
        except OSError: continue
        with it:
            for e in it:
                try: st=e.stat(follow_symlinks=False)
                except OSError: continue
                n+=1
                if e.is_dir(follow_symlinks=False): stack.append(e.path)
                elif st.st_nlink>1:
                    k=(st.st_dev,st.st_ino)
                    if k in seen: continue
                    seen.add(k)
                total+=st.st_blocks*512
    return total,n
root=sys.argv[1]; mode=sys.argv[2]
t=time.perf_counter()
if mode=="single": tot,n=walk(root)
else:
    kids=[e.path for e in os.scandir(root) if e.is_dir(follow_symlinks=False)]
    with ThreadPoolExecutor(10) as ex: r=list(ex.map(walk,kids))
    tot=sum(a for a,_ in r); n=sum(b for _,b in r)
print(f"python-{mode}: {time.perf_counter()-t:.1f}s  {tot} bytes  {n} entries")
