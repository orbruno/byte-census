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
    # The parent scans the root's own entries exactly as walk() would, then
    # dispatches each child directory's descendants to a worker.
    kids, root_total, root_n, root_links = [], 0, 0, set()
    with os.scandir(root) as it:
        for e in it:
            try: st=e.stat(follow_symlinks=False)
            except OSError: continue
            root_n+=1
            if e.is_dir(follow_symlinks=False): kids.append(e.path)
            elif st.st_nlink>1:
                root_links.add((st.st_dev,st.st_ino,st.st_blocks)); continue
            root_total+=st.st_blocks*512
    with ProcessPoolExecutor(workers) as ex: r=list(ex.map(walk,kids))
    links=root_links.union(*(x[2] for x in r))  # global hard-link dedupe at merge
    tot=root_total+sum(x[0] for x in r)+sum(b*512 for _,_,b in links); n=root_n+sum(x[1] for x in r)
    print(f"python-processes-{workers}: {time.perf_counter()-t:.1f}s  {tot} bytes  {n} entries")
