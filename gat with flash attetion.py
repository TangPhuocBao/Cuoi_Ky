import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import MessagePassing
from torch_geometric.utils import add_self_loops, softmax
from torch_geometric.data import Data
import math

try:
    from flash_attn import flash_attn_func
    FLASH_ATTENTION_AVAILABLE = True
except ImportError:
    FLASH_ATTENTION_AVAILABLE = False
    print("Flash Attention không có sẵn. Sử dụng attention thông thường.")


class FlashGATConv(MessagePassing):
    """
    Graph Attention Layer với Flash Attention tích hợp
    """
    def __init__(self, in_channels, out_channels, heads=1, concat=True, 
                 negative_slope=0.2, dropout=0.0, use_flash=True, bias=True):
        super(FlashGATConv, self).__init__(aggr='add', node_dim=0)
        
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.heads = heads
        self.concat = concat
        self.negative_slope = negative_slope
        self.dropout = dropout
        self.use_flash = use_flash and FLASH_ATTENTION_AVAILABLE
        
        # Linear transformation cho mỗi head
        self.lin = nn.Linear(in_channels, heads * out_channels, bias=False)
        
        if not self.use_flash:
            # Attention mechanism truyền thống
            self.att_src = nn.Parameter(torch.Tensor(1, heads, out_channels))
            self.att_dst = nn.Parameter(torch.Tensor(1, heads, out_channels))
        
        if bias and concat:
            self.bias = nn.Parameter(torch.Tensor(heads * out_channels))
        elif bias and not concat:
            self.bias = nn.Parameter(torch.Tensor(out_channels))
        else:
            self.register_parameter('bias', None)
        
        self.reset_parameters()
    
    def reset_parameters(self):
        nn.init.xavier_uniform_(self.lin.weight)
        if not self.use_flash:
            nn.init.xavier_uniform_(self.att_src)
            nn.init.xavier_uniform_(self.att_dst)
        if self.bias is not None:
            nn.init.zeros_(self.bias)
    
    def forward(self, x, edge_index, return_attention_weights=False):
        """
        Args:
            x: Node features [num_nodes, in_channels]
            edge_index: Graph connectivity [2, num_edges]
            return_attention_weights: Trả về attention weights hay không
        """
        num_nodes = x.size(0)
        
        # Linear transformation
        x = self.lin(x).view(-1, self.heads, self.out_channels)
        
        # Add self-loops
        edge_index, _ = add_self_loops(edge_index, num_nodes=num_nodes)
        
        if self.use_flash:
            out = self.flash_attention_propagate(x, edge_index)
        else:
            out = self.propagate(edge_index, x=x, num_nodes=num_nodes)
        
        if self.concat:
            out = out.view(-1, self.heads * self.out_channels)
        else:
            out = out.mean(dim=1)
        
        if self.bias is not None:
            out = out + self.bias
        
        if return_attention_weights:
            # Tính attention weights để visualization
            alpha = self.compute_attention_weights(x, edge_index)
            return out, (edge_index, alpha)
        
        return out
    
    def flash_attention_propagate(self, x, edge_index):
        """
        Propagate sử dụng Flash Attention
        """
        num_nodes = x.size(0)
        row, col = edge_index
        
        # Prepare queries, keys, values
        q = x[row]  # [num_edges, heads, out_channels]
        k = x[col]  # [num_edges, heads, out_channels]
        v = x[col]  # [num_edges, heads, out_channels]
        out = torch.zeros_like(x)
        
        for node_idx in range(num_nodes):

            mask = row == node_idx
            if mask.sum() == 0:
                continue
            
            q_node = q[mask].unsqueeze(0)  # [1, num_neighbors, heads, dim]
            k_node = k[mask].unsqueeze(0)
            v_node = v[mask].unsqueeze(0)
            
            q_node = q_node.transpose(1, 2)  # [1, heads, num_neighbors, dim]
            k_node = k_node.transpose(1, 2)
            v_node = v_node.transpose(1, 2)
            scale = 1.0 / math.sqrt(self.out_channels)
            attn_weights = torch.matmul(q_node, k_node.transpose(-2, -1)) * scale
            attn_weights = F.softmax(attn_weights, dim=-1)
            attn_weights = F.dropout(attn_weights, p=self.dropout, training=self.training)
            
            attn_out = torch.matmul(attn_weights, v_node)  # [1, heads, num_neighbors, dim]
            out[node_idx] = attn_out.mean(dim=2).squeeze(0)  # Average over neighbors
        
        return out
    
    def message(self, x_j, x_i, index, ptr, size_i):
        """
        Tính message từ node j đến node i (attention truyền thống)
        """
        # Tính attention coefficients
        alpha = (x_i * self.att_src).sum(dim=-1) + (x_j * self.att_dst).sum(dim=-1)
        alpha = F.leaky_relu(alpha, self.negative_slope)
        alpha = softmax(alpha, index, ptr, size_i)
        alpha = F.dropout(alpha, p=self.dropout, training=self.training)
        
        return x_j * alpha.unsqueeze(-1)
    
    def compute_attention_weights(self, x, edge_index):
        """
        Tính attention weights cho visualization
        """
        row, col = edge_index
        if self.use_flash:
            # Simplified attention computation
            alpha = torch.ones(edge_index.size(1), self.heads, device=x.device)
        else:
            alpha = (x[row] * self.att_src).sum(dim=-1) + (x[col] * self.att_dst).sum(dim=-1)
            alpha = F.leaky_relu(alpha, self.negative_slope)
            alpha = softmax(alpha, row, num_nodes=x.size(0))
        
        return alpha


class GAT(nn.Module):
    """
    Multi-layer Graph Attention Network
    """
    def __init__(self, in_channels, hidden_channels, out_channels, 
                 num_layers=2, heads=8, dropout=0.6, use_flash=True):
        super(GAT, self).__init__()
        
        self.num_layers = num_layers
        self.dropout = dropout
        
        self.convs = nn.ModuleList()
        
        # First layer
        self.convs.append(
            FlashGATConv(in_channels, hidden_channels, heads=heads, 
                        dropout=dropout, use_flash=use_flash)
        )
        
        # Hidden layers
        for _ in range(num_layers - 2):
            self.convs.append(
                FlashGATConv(hidden_channels * heads, hidden_channels, 
                           heads=heads, dropout=dropout, use_flash=use_flash)
            )
        
        # Output layer
        self.convs.append(
            FlashGATConv(hidden_channels * heads, out_channels, 
                        heads=1, concat=False, dropout=dropout, use_flash=use_flash)
        )
    
    def forward(self, x, edge_index):
        for i, conv in enumerate(self.convs[:-1]):
            x = conv(x, edge_index)
            x = F.elu(x)
            x = F.dropout(x, p=self.dropout, training=self.training)
        
        x = self.convs[-1](x, edge_index)
        return F.log_softmax(x, dim=1)
