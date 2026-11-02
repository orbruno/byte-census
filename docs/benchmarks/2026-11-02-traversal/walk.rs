use std::{collections::HashSet, fs, os::unix::fs::MetadataExt, path::PathBuf, sync::{Arc, Mutex}, thread, time::Instant};
fn main() {
    let root = PathBuf::from(std::env::args().nth(1).unwrap());
    let threads: usize = std::env::args().nth(2).unwrap().parse().unwrap();
    let t = Instant::now();
    let queue = Arc::new(Mutex::new((vec![root], 0usize))); // (stack, active)
    let seen = Arc::new(Mutex::new(HashSet::new()));
    let mut hs = vec![];
    for _ in 0..threads {
        let (q, seen) = (queue.clone(), seen.clone());
        hs.push(thread::spawn(move || {
            let (mut tot, mut n) = (0u64, 0u64);
            loop {
                let d = { let mut g = q.lock().unwrap();
                    match g.0.pop() { Some(d) => { g.1 += 1; d } None => { if g.1 == 0 { break } drop(g); thread::yield_now(); continue } } };
                let mut local = vec![];
                if let Ok(rd) = fs::read_dir(&d) { for e in rd.flatten() {
                    let Ok(m) = fs::symlink_metadata(e.path()) else { continue };
                    n += 1;
                    if m.is_dir() { local.push(e.path()); }
                    else if m.nlink() > 1 && !seen.lock().unwrap().insert((m.dev(), m.ino())) { continue }
                    tot += m.blocks() * 512;
                }}
                let mut g = q.lock().unwrap(); g.0.extend(local); g.1 -= 1;
            }
            (tot, n)
        }));
    }
    let (mut tot, mut n) = (0, 0);
    for h in hs { let (a, b) = h.join().unwrap(); tot += a; n += b; }
    println!("rust-{threads}: {:.1}s  {:.2} GB  {n} entries", t.elapsed().as_secs_f64(), tot as f64 / 1e9);
}
