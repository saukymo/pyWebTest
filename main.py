import argparse
import time
import multiprocessing
import threading
import Queue
import urllib2
from datetime import datetime

class AgentGroup():
	def __init__(self, queue, num_threads, run_time, rampup):
		self.queue = queue
		self.num_threads = num_threads
		self.run_time = run_time
		self.rampup = rampup
		self.details = []

	def run(self):
		self.start_time = time.time()
		threads = []
		for idx in range(self.num_threads):
			spacing = 1.0 * self.rampup / self.num_threads
			if idx > 0:
				time.sleep(spacing)

			agent = Agent(self.queue, idx, self.run_time, self.start_time)
			agent.daemon = True
			threads.append(agent)
			agent.start()

		for agent in threads:
			agent.join()
			self.details.append("%5d\t%9.2f\t%8d\t%6d\t%14d\t%23.3f\t%23.3f" % (agent.thread_num, agent.real_start_time - self.start_time, agent.trans_count, agent.errors, agent.received_data, agent.avg_resp_time, agent.avg_throughput))

class Agent(threading.Thread):
	"""
		Every single thread to run the test code.
		Test stastics put into threads queue.
	"""
	def __init__(self, queue, thread_num, run_time, start_time):
		threading.Thread.__init__(self)
		self.queue = queue
		self.thread_num = thread_num
		self.run_time = run_time
		self.start_time = start_time
		self.real_start_time = time.time()
		self.trans_count = 0
		self.received_data = 0
		self.errors = 0
		self.avg_resp_time = 0
		self.avg_throughput = 0

	def run(self):
		elapsed_time = 0
		total_resp_time = 0
		while elapsed_time < self.run_time:
			error = ''
			start = time.time()
			resp_data = 0

			try:
				connect = urllib2.urlopen(url)
				content = connect.read()
				resp_data = len(content)
			except Exception, e:
				error = str(e)

			run_time = time.time() - start
			elapsed_time = time.time() - self.start_time

			self.trans_count += 1
			self.received_data += resp_data
			if error != '':
				self.errors += 1 
			total_resp_time += run_time

			fields = (self.thread_num, elapsed_time, run_time, resp_data, error)
			# print fields
			self.queue.put(fields)

		self.avg_resp_time = 1.0 * total_resp_time / self.trans_count	
		self.avg_throughput = 1.0 * self.trans_count / (time.time() - self.real_start_time)

class QueueReader(threading.Thread):
	def __init__(self, queue):
		threading.Thread.__init__(self)
		self.queue = queue
		self.trans_count = 0
		self.error_count = 0
		self.elapsed_time = 0.0

	def run(self):
		with open("results.csv", "w") as f:
			while True:
				try:
					agent_num, elapsed_time, run_time, resp_data, error = self.queue.get(False)
					self.trans_count += 1
					if error != '':
						error = '\\n'.join(error.splitlines())

						self.error_count += 1
					f.write('%d, %d, %0.3f, %f, %d, %s,\n' % (self.trans_count, agent_num, elapsed_time, run_time, resp_data, error))
					# print agent_num, self.trans_count, elapsed_time, run_time, resp_data, error
					if elapsed_time > self.elapsed_time:
						self.elapsed_time = elapsed_time

					if elapsed_time < test_duration:
						# print int(elapsed_time / interval_time), elapsed_time, interval_time
						interval_run_time[int(elapsed_time / interval_time)].append(run_time)
					f.flush()
				except Queue.Empty:
					time.sleep(.05)

def average(seq):
    avg = (float(sum(seq)) / len(seq))
    return avg

def standard_dev(seq):
    avg = average(seq)
    sdsq = sum([(i - avg) ** 2 for i in seq])
    try:
        stdev = (sdsq / (len(seq) - 1)) ** .5
    except ZeroDivisionError:
        stdev = 0
    return stdev

def percentile(seq, percentile):
    i = int(len(seq) * (percentile / 100.0))
    seq.sort()
    return seq[i]


arg_parser = argparse.ArgumentParser()

arg_parser.add_argument('-a', nargs='?', help='number of agents', default=2)
arg_parser.add_argument('-d', nargs='?', help='test duration in seconds', default=10)
arg_parser.add_argument('-i', nargs='?', help='number of time-seriels interval', default=10)
arg_parser.add_argument('-r', nargs='?', help='rampup in seconds', default=0.0)
arg_parser.add_argument('-u', help='test target url', required=True) 
args = vars(arg_parser.parse_args())
# print args
# print args.get('a'), args.get('d')

url = args.get('u')
test_duration = int(args.get('d'))
interval = int(args.get('i'))
interval_time = test_duration / interval
interval_run_time = [[] for _ in range(interval)]

queue = multiprocessing.Queue()
queue_reader = QueueReader(queue)
queue_reader.daemon = True
queue_reader.start()

ag = AgentGroup(queue, int(args.get('a')), test_duration, int(args.get('r')))

test_start_timestamp = time.time()
ag.run()
test_end_timestamp = time.time()

all_run_time = []
for interval_time_list in interval_run_time:
	all_run_time.extend(interval_time_list)

print "\n===Summary==="
print "transactions: %d hits" % (queue_reader.trans_count)
print "errors: %d" % (queue_reader.error_count)
print "runtime: %d secs" % (test_duration)
print "rampup: %d secs" % (int(args.get('r')))
print "time-series interval: %0.3f secs" % (interval_time)
print ""

print "test start: %s" % (datetime.fromtimestamp(test_start_timestamp).strftime("%Y-%m-%d %H:%M:%S"))
print "test finish: %s" % (datetime.fromtimestamp(test_end_timestamp).strftime("%Y-%m-%d %H:%M:%S"))
print "\n===All Transactions==="
print "Response Time Summary (secs):"
print "%7s\t%7s\t%7s\t%7s\t%7s\t%7s\t%7s\t%7s" % ("count", "avg", "min", "50pct", "80pct", "90pct", "max", "stdev")
print "%7d\t%7.3f\t%7.3f\t%7.3f\t%7.3f\t%7.3f\t%7.3f\t%7.3f\n" % (len(all_run_time), average(all_run_time), min(all_run_time), percentile(all_run_time, 50),\
 percentile(all_run_time, 80), percentile(all_run_time, 90), max(all_run_time), standard_dev(all_run_time))

print "Interval Details (secs):"
print "%8s\t%7s\t%7s\t%7s\t%7s\t%7s\t%7s\t%7s\t%7s" % ("interval", "count", "avg", "min", "50pct", "80pct", "90pct", "max", "stdev")
for interval_num in range(interval):
	interval_list = interval_run_time[interval_num]
	print "%8d\t%7d\t%7.3f\t%7.3f\t%7.3f\t%7.3f\t%7.3f\t%7.3f\t%7.3f" % (interval_num, len(interval_list), average(interval_list), min(interval_list), percentile(interval_list, 50),\
 percentile(interval_list, 80), percentile(interval_list, 90), max(interval_list), standard_dev(interval_list))

print "\n===Agent Details==="
print "Agent\tStarttime\tRequests\tErrors\tBytes received\tAvg Response Time(secs)\tAvg throughput(req/sec)"
for agent_detail in ag.details:
	print agent_detail




