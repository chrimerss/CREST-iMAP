from mpi4py import MPI

comm= MPI.COMM_WORLD
print('%d of %d'%(comm.Get_rank(), comm.Get_size()))
