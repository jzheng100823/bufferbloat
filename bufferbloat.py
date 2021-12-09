from mininet.topo import Topo
from subprocess import Popen
import os
from time import sleep
from time import time
from numpy import mean, std
from mininet.node import CPULimitedHost, OVSController
from mininet.link import TCLink
from mininet.net import Mininet
from mininet.log import lg, info
from mininet.util import dumpNodeConnections
from subprocess import call
from multiprocessing import Process
from monitor import *
import matplotlib

class BBTopo(Topo):
    "Simple topology for bufferbloat experiment."
    
    def __init__(self, queue_size):
        super(BBTopo, self).__init__()

        # Create switch s0 (the router)
        self.addSwitch('s0')
        
        # TODO: Create two hosts with names 'h1' and 'h2'
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')

        # TODO: Add links with appropriate bandwidth, delay, and queue size parameters.
        # Set the router queue size using the queue_size argument
        # Set bandwidths/latencies using the bandwidths and minimum RTT given in the network diagram above
        self.addLink('h1', 's0', bw=1000, delay='20ms', max_queue_size=queue_size)
        self.addLink('h2', 's0', bw=1.5, delay='20ms', max_queue_size=queue_size) 

        return
 
def start_iperf(net, experiment_time):
    # Start a TCP server on host 'h2' using perf.
    # The -s parameter specifies server mode
    # The -w 16m parameter ensures that the TCP flow is not receiver window limited (not necessary for client)
    print "Starting iperf server"
    h2 = net.get('h2')
    server = h2.popen("iperf -s -w 16m", shell=True)

    # TODO: Start an TCP client on host 'h1' using iperf.
    # Ensure that the client runs for experiment_time seconds
    print "Starting iperf client"
    h1 = net.get('h1')
    client = h1.popen("iperf -c {0} -t {1}".format(h2.IP(), experiment_time), shell=True)

def start_ping(net, outfile="pings.txt"):
    # TODO: Start a ping train from h1 to h2 with 0.1 seconds between pings, redirecting stdout to outfile
    print "Starting ping train"
    h1 = net.get('h1')
    h2 = net.get('h2')
    h1.popen("sudo ping -i 0.1 " + h2.IP() + " > " + outfile, shell=True)

def start_tcpprobe(outfile="cwnd.txt"):
    Popen("sudo cat /proc/net/tcpprobe > " + outfile, shell=True)
    
def stop_tcpprobe():
    Popen("killall -9 cat", shell=True).wait()

def start_qmon(iface, interval_sec=.1, outfile="q.txt"):
    monitor = Process(target=monitor_qlen, args=(iface, interval_sec, outfile))
    monitor.start()
    return monitor

def start_webserver(net):
    h1 = net.get('h1')
    proc = h1.popen("python http/webserver.py", shell=True)
    sleep(1)
    return [proc]
    
def fetch_webserver(net, experiment_time):
    h2 = net.get('h2')
    h1 = net.get('h1')
    download_times = []

    start_time = time()
    while True:
        sleep(3)
        now = time()
        if now - start_time > experiment_time:
            break
        fetch = h2.popen("curl -o /dev/null -s -w %{time_total} ", h1.IP(), shell=True)
        download_time, _ = fetch.communicate()
        print "Download time: {0}, {1:.1f}s left...".format(download_time, experiment_time - (now-start_time))
        download_times.append(float(download_time))

    average_time = mean(download_times)
    std_time = std(download_times)
    print "\nDownload Times: {}s average, {}s stddev\n".format(average_time, std_time)

def bufferbloat(queue_size, experiment_time, experiment_name):
    # Don't forget to use the arguments!

    # Set the cwnd control algorithm to "reno" (half cwnd on 3 duplicateacks)
    # Modern Linux uses CUBIC-TCP by default that doesn't have the usual sawtooth
    # behaviour. For those who are curious, replace reno with cubic
    # see what happens...
    os.system("sysctl -w net.ipv4.tcp_congestion_control=reno")

    # create the topology and network
    topo = BBTopo(queue_size)
    net = Mininet(topo=topo, host=CPULimitedHost, link=TCLink, controller= OVSController)
    net.start()
    
    # Print the network topology
    dumpNodeConnections(net.hosts)

    # Performs a basic all pairs ping test to ensure the network set upproperly
    net.pingAll()

    # Start monitoring TCP cwnd size
    outfile = "{}_cwnd.txt".format(experiment_name)
    start_tcpprobe(outfile)
    
    # TODO: Start monitoring the queue sizes with the start_qmon() function.
    # Fill in the iface argument with "s0-eth2" if the link from s0 to h2
    # is added second in BBTopo or "s0-eth1" if the link from s0 to h2
    # is added first in BBTopo. This is because we want to measure the
    # number of packets in the outgoing queue from s0 to h2.
    outfile = "{}_qsize.txt".format(experiment_name)
    qmon = start_qmon(iface="s0-eth2", interval_sec=.01, outfile=outfile)
    
    # TODO: Start the long lived TCP connections with the start_iperf()function
    start_iperf(net, experiment_time)

    # TODO: Start pings with the start_ping() function
    outfile = "{}_pings.txt".format(experiment_name)
    start_ping(net, outfile)
 
    # TODO: Start the webserver with the start_webserver() function
    start_webserver(net)

    # TODO: Measure and print website download times with the fetch_webserver() function
    fetch_webserver(net, experiment_time)

    # Stop probing
    stop_tcpprobe()
    qmon.terminate()
    net.stop()

    # Ensure that all processes you create within Mininet are killed.
    Popen("pgrep -f webserver.py | xargs kill -9", shell=True).wait()
    call(["mn", "-c"])

#%matplotlib inline
from plot_cwnd import plot_congestion_window
from plot_qsize import plot_queue_length
from plot_ping import plot_ping_rtt

def plot_measurements(experiment_name_list, cwnd_histogram=False):

    # plot the congestion window over time
    for name in experiment_name_list:
        cwnd_file = "{}_cwnd.txt".format(name)
        plot_congestion_window(cwnd_file, histogram=cwnd_histogram)

    # plot the queue size over time
    for name in experiment_name_list:
        qsize_file = "{}_qsize.txt".format(name)
        plot_queue_length(qsize_file)
 
    # plot the ping RTT over time
    for name in experiment_name_list:
        ping_file = "{}_pings.txt".format(name)
        plot_ping_rtt(ping_file)

if __name__ == "__main__":
    call(["mn", "-c"])
    # TODO: call the bufferbloat function twice, once with queue size of 20packets and once with a queue size of 100.
    testNames = {'test100', 'test20'}
    testList = list(testNames)
    bufferbloat(100, 10, testList[0])
    bufferbloat(20, 10, testList[1])

    #TODO: Call plot_measurements() to plot your results
    testList = list(testNames)
    plot_measurements(testList)
