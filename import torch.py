import torch
import math

class gc(torch.nn.Module):
    def __init__(self, in_features, out_features, bias=True):
        self.in_features= in_features
        self.out_features= out_features
        super(gc, self).__init__()
        if bias:
            self.bias = torch.nn.Parameter(torch.FloatTensor(out_features))
        else:
            self.register_parameter('bias', None)
        self.reset_parameters()
    def reset_parameters(self):
        stdv = 1. / math.sqrt(self.weight.size(1))
        self.weight.data.uniform_(-stdv, stdv)
        if self.bias is not None:
            self.bias.data.uniform_(-stdv, stdv)
    def forward(self, input, adj):
        suport= torch.mm(input, self.weight)
        output= torch.spmm(adj, suport)
        if self.bias is not None:
            return output + self.bias
        else:
            return output
    def __repr__(self):
        return self.__class__.__name__ + ' ('+ str(self.in_features) + ' -> ' + str(self.out_features) + ')'    
class GraphConvolutionalNetwork(torch.nn.Module):
    def __init__(self, nfeat, nhid, nclass, dropout= 0.5):
        super(GraphConvolutionalNetwork, self).__init__()
        self.gc1 = gc(nfeat, nhid)
        self.gc2 = gc(nhid, nclass)
        self.dropout = dropout
    def forward(self, x, adj):
        x = torch.nn.functional.relu(self.gc1(x, adj))
        x = torch.nn.functional.dropout(x, self.dropout, training=self.training)
        x = self.gc2(x, adj)
        return torch.nn.functional.log_softmax(x, dim=1)
def normalize_adj(adj):
    rowsum = torch.sum(adj, dim=1)
    d_inv_sqrt = torch.pow(rowsum, -0.5).flatten()
    d_inv_sqrt[torch.isinf(d_inv_sqrt)] = 0.
    d_mat_inv_sqrt = torch.diag(d_inv_sqrt)
    return torch.mm(torch.mm(d_mat_inv_sqrt, adj), d_mat_inv_sqrt)    

if __name__ == '__main__':
    





