## Asynchronous IO
First introduced in Python 3.8, asynchronous IO allow you to create server clients in a much more elegant way.

The `asyncio` philosophy differs from the convenient programming style and can look confusing at the very beginning. I would recommend this learn materials to make yourself familiar with the basics:

* [26 min video with basics](https://www.youtube.com/watch?v=t5Bo1Je9EmE&pp=ugMICgJydRABGAE%3D)
* [Official python 3.10 asyncio documentation](https://docs.python.org/3.10/library/asyncio.html) 

In case of this particular server it is possible to handle ZMQ stream in more appropriate way. Instead of continouns polling of messages from ZMQ stream
> before:
>```python
>context = zmq.Context()
>socket = context.socket(zmq.SUB)
>while True:
>    try:
>        msg = socket.recv(flags=zmq.NOBLOCK)
>    except zmq.ZMQError:
>        # no packet more in the stream
>    time.sleep(0.25)
>```

they can be received asynchronously that program "awaits" each oncoming message

> after:
>```python
>context = zmq.asyncio.Context()
>socket = context.socket(zmq.SUB)
>while True:
>    msg = await socket.recv()
>```

The TangoDS can work in asynchronous IO mode too if the variable `green_mode` set to `tango.GreenMode.Asyncio`. In this case we are able to use the save `event_loop` for asynchronous receive of ZMQ packets from detector and tango communication as well.


## Multiprocessing
Usually concurrency in most of programming languages (as Java, or C++) is using threads. One of the features of the python language, namely the implementation of its default interpreter CPython is the so-called [global interpreter lock (GIL)](https://en.wikipedia.org/wiki/Global_interpreter_lock) which actually allows to run only one thread at the same time. However, there are ways to bypass this feature with standard language methods.

There is a [`multiprocessing`](https://docs.python.org/3.10/library/multiprocessing.html) package for this, which creates additional processes (which are not actually threads but do the same thing). There are various high API tools to make a program which utilizes more than one core of the CPU.

### Thread-safe variables
The main difference in the development of the multiprocessing programs compared to the single thread programs is the synchronization between processes. This means that even the most commong operations as reading or assigning a variable's value need to be thread-safe.

Here is an example how a simple incrementing the value `counter` from by 1 two processes can cause a problem:
``` mermaid
sequenceDiagram
    Process A->>+Memory: read counter value
    Memory->>Process A: read counter = 0
    Process B->>+Memory: read counter value
    Memory->>Process B: read counter = 0
    Process A-->Process A: incrementing counter by 1
    Process A->>+Memory: write counter =  1
    Process B-->Process B: incrementing counter by 1
    Process B->>+Memory: write counter =  1
```
So the `counter` value which expected to be 2 will be 1. The reason of it is the fact that incrementing a variable is not an [atomic operation](https://en.wikipedia.org/wiki/Linearizability) itself and consists of one read operation and then write operation. Actually (depending on the CPU and programming language architecture) read and write operations itself can be not atomic. Thus, we need a synchronization between two threads in order to perform the operations in the right order.

The most trivial example is so called [mutex](https://en.wikipedia.org/wiki/Mutual_exclusion). This is an object shared between processes which can be acquired or released. While the shared lock is acquired by one of the processes the other processes will wait till it is released. Here is the upper example with using a lock:

``` mermaid
sequenceDiagram
    Process A->>+Shared lock: acquire lock
    Process B-->>Shared lock: try acquire lock
    Shared lock-->>Process B: lock is already acquired by Process A
    Process A->>+Memory: read counter value
    Memory->>Process A: read counter = 0
    Process A-->Process A: incrementing counter by 1
    Process A->>+Memory: write counter =  1
    Process A->>+Shared lock: release lock
    Process B->>+Shared lock: acquire lock
    Process B->>+Memory: read counter value
    Memory->>Process B: read counter = 1
    Process B-->Process B: incrementing counter by 1
    Process B->>+Memory: write counter =  2
    Process B->>+Shared lock: release lock
```
The classes for synchronization are available in `multiprocessing` library. Here is the upper example implemented in python:

```python
# initialize a shared lock instance
shared_lock = multiprocessing.Lock()

# initialize a shared integer variable
shared_counter = multiprocessing.Value("i", 0)

# function which will be executed in the process A
def func_A(lock, counter):
    lock.acquire()
    counter += 1
    print(counter)
    lock.release()

# function which will be executed in the process B
def func_B(lock, counter):
    lock.acquire()
    counter += 1
    print(counter)
    lock.release()

# create a pool with two processes
process_pool = multiprocessing.ProcessPoolExecutor(2)

# assign to run a function func_A with
# the args shared_lock and shared_counter with one of the process in pool
process_pool.submit(func_A, shared_lock, shared_counter)

# assign to run a function func_B with
# the args shared_lock and shared_counter with one of the process in pool
process_pool.submit(func_B, shared_lock, shared_counter)

# Output:
# 1
# 2
```

However, there are only basic data types as scalar `Value` and only 1D array `Array` available. The  $n \times m$ 2D array can be possibly stored as 1D array with the length of $l = n \cdot m$. But it is painful to read, reshape, perform an operation, reshape again and store an array. Is it possible to have a shared `numpy` array?

Yes, but it is a little bit complex In python 3.8 a shared memory feature was introduced and this allows to work directly with a memory space and use than assign a `numpy` array to work with it. Here is an example of creating this kind of `numpy`array:
```python
# a manager which allocates the shared memory
shared_memory_manager =  multiprocessing.managers.SharedMemoryManager()
# get how many bytes need to be allocated and shared for an 400x400 float numpy array
# the values of this array will be never used 
array_length = np.zeros([400, 400], dtype=float).nbytes
# saving the pointer to the shared memory
mem_pointer = shared_memory_manager.SharedMemory(size=array_length)
# assign to a numpy array to store its values
# under the given shared memory address
numpy_array = np.ndarray((400, 400), dtype=float, buffer=mem_pointer.buf)
```

Learn more:

* [Official python 3.10 shared memory documentation](https://docs.python.org/3.10/library/multiprocessing.shared_memory.html)
* [Comprehensive example](https://luis-sena.medium.com/sharing-big-numpy-arrays-across-python-processes-abf0dc2a0ab2)
