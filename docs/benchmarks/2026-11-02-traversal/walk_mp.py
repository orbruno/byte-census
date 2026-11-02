import os, sys, time
from concurrent.futures import ProcessPoolExecutor
def walk(root):
    total=n=0; links=set(); stack=[root]
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
                    links.add((st.st_dev,st.st_ino,st.st_blocks)); continue
                total+=st.st_blocks*512
    return total,n,links
if __name__=="__main__":
    root=sys.argv[1]; workers=int(sys.argv[2]); t=time.perf_counter()
    kids=[e.path for e in os.scandir(root) if e.is_dir(follow_symlinks=False)]
    with ProcessPoolExecutor(workers) as ex: r=list(ex.map(walk,kids))
    links=set().union(*(x[2] for x in r))  # global hard-link dedupe at merge
    tot=sum(x[0] for x in r)+sum(b*512 for _,_,b in links); n=sum(x[1] for x in r)
    print(f"python-processes-{workers}: {time.perf_counter()-t:.1f}s  {tot/1e9:.2f} GB  {n} entries")
