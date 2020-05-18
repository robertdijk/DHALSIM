from mininet.net import Mininet
from mininet.cli import CLI
from minicps.mcps import MiniCPS
from topo import ScadaTopo
import sys
import time
import shlex
import subprocess
import signal


automatic = 1
mitm_attack = 1

class Minitown(MiniCPS):
    """ Script to run the Minitown SCADA topology """

    def __init__(self, name, net):
        net.start()

        r0 = net.get('r0')
        # Pre experiment configuration, prepare routing path
        r0.cmd('sysctl net.ipv4.ip_forward=1')

        self.sender_plcs =  [2, 4, 6, 7, 9]
        self.receiver_plcs = [1, 3, 5]

        self.sender_plcs_nodes = []
        self.receiver_plcs_nodes = []

        self.sender_plcs_files = []
        self.receiver_plcs_files = []

        self.sender_plcs_processes = []
        self.receiver_plcs_processes = []

        if automatic:
            self.automatic_start()
        else:
            CLI(net)
        net.stop()

    def automatic_start(self):
        self.create_log_files()

        # Because of our sockets, we gotta launch all the PLCs "sending" variables first
        index = 0
        for plc in self.sender_plcs:
            self.sender_plcs_nodes.append(net.get('plc' + str( self.sender_plcs[index] ) ) )

            self.sender_plcs_files.append( open("output/plc" + str( self.sender_plcs[index]) + ".log", 'r+' ) )
            self.sender_plcs_processes.append( self.sender_plcs_nodes[index].popen(sys.executable, "automatic_plc.py", "-n", "plc" + str(self.sender_plcs[index]), stderr=sys.stdout,
                                                         stdout=self.sender_plcs_files[index]) )
            print("Launched plc" + str(self.sender_plcs[index]))
            index += 1
            time.sleep(0.2)

        # After the servers are done, we can launch the client PLCs
        index = 0
        for plc in self.receiver_plcs:
            self.receiver_plcs_nodes.append(net.get('plc' + str( self.receiver_plcs[index] ) ) )
            self.receiver_plcs_files.append( open("output/plc" + str(self.receiver_plcs[index]) + ".log", 'r+') )
            self.receiver_plcs_processes.append( self.receiver_plcs_nodes[index].popen(sys.executable, "automatic_plc.py", "-n", "plc" + str(self.receiver_plcs[index]), stderr=sys.stdout,
                                                         stdout=self.receiver_plcs_files[index]) )
            print("Launched plc" + str(self.receiver_plcs[index]))
            index += 1
            time.sleep(0.2)

        physical_output = open("output/physical.log", 'r+')
        print "[*] Launched the PLCs and SCADA process, launching simulation..."
        plant = net.get('plant')

        simulation_cmd = shlex.split("python automatic_plant.py -s pdd -t ctown -o physical_process.csv")
        self.simulation = plant.popen(simulation_cmd, stderr=sys.stdout, stdout=physical_output)
        print "[] Simulating..."

        # Launching automatically mitm attack
        self.attacker = None
        self.attacker_file = None
        self.attacker_process = None
        if mitm_attack == 1 :
            self.attacker = net.get('attacker')
            self.attacker_file =  open("output/attacker.log", 'r+')
            self.attacker_process = self.attacker.popen(sys.executable, "/home/mininet/WadiTwin/attack_repository/mitm_plc_plc/automatic_ctown_mitm_attack.py", "-a", "mitm", "-t", "plc5", stderr=sys.stdout,
                                                         stdout=self.attacker_file)
        print "[] Attacking"

        try:
            while self.simulation.poll() is None:
                pass
        except KeyboardInterrupt:
            print "Cancelled, finishing simulation"
            self.force_finish()
            return

        self.finish()

    def create_log_files(self):
        cmd = shlex.split("./create_log_files.sh")
        subprocess.call(cmd)

    def force_finish(self):

        for plc in self.receiver_plcs_processes:
            plc.kill()

        for plc in self.sender_plcs_processes:
            plc.kill()

        self.simulation.kill()

        cmd = shlex.split("./kill_cppo.sh")
        subprocess.call(cmd)

        net.stop()
        sys.exit(1)

    def end_plc_process(self, plc_process):

        plc_process.send_signal(signal.SIGINT)
        plc_process.wait()
        if plc_process.poll() is None:
            plc_process.terminate()
        if plc_process.poll() is None:
            plc_process.kill()


    def finish(self):

        #toDo: We have to handle differently the finish process, ideally we want to:
        #   Send a SIGINT signal to the PLCS
        #   Register a signal handler to gracefully handle that signal
        #   If the processes still exist after the SIGINT (they shouldn't) we send a SIGKILL
        print "[*] Simulation finished"

        index = 0
        for plc in self.receiver_plcs_processes:
            print "[] Terminating PLC" + str(self.receiver_plcs[index])
            self.end_plc_process(plc)
            print "[*] PLC" + str(self.receiver_plcs[index]) + " terminated"
            index += 1

        index = 0
        for plc in self.sender_plcs_processes:
            print "[] Terminating PLC" + str(self.sender_plcs[index])
            self.end_plc_process(plc)
            print "[*] PLC" + str(self.sender_plcs[index]) + " terminated"
            index += 1

        self.end_plc_process(self.attacker_process)
        print "[*] All processes terminated"

        if self.simulation:
            self.simulation.terminate()

        cmd = shlex.split("./kill_cppo.sh")
        subprocess.call(cmd)
        net.stop()
        sys.exit(0)

if __name__ == "__main__":
    topo = ScadaTopo()
    net = Mininet(topo=topo)
    minitown_cps = Minitown(name='minitown', net=net)