# -*- coding: utf-8 -*-
"""
Created on Sun Dec 30 16:14:04 2018

@author: truthless
"""

import random
import numpy as np
import torch
import torch.utils.data as data

PAD = 0
UNK = 1 #OOV
GO = 2
EOS = 3
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

class DataManager:
    
    def __init__(self, path, no_pretrain_word2vec, dim, context_len):
               
        #read text
        self.text = {}
        for name in ["train", "valid", "test"]:
            self.text[name] = []
            with open("{0}/{1}.txt".format(path, name)) as fl:
                for line in fl:
                    utterances = line.strip().lower().split('\t')
                    utterances = [''] * (context_len - len(utterances)) + utterances
                    self.text[name].append([utterances[-context_len:-1], utterances[-1]])

        #arrange words
        wordscount = {}
        for name in ["train", "valid"]:
            texts = self.text[name]
            for item in texts:
                words = item[0][-1].split() + item[1].split()
                for word in words:
                    if word in wordscount:
                        wordscount[word] += 1
                    else:
                        wordscount[word] = 1
        wordssorted = sorted(wordscount.items(), key = lambda d: (d[1],d[0]), reverse=True) 
        self.word2index = {'<PAD>':0, '<UNK>':1, '<GO>':2, '<EOS>':3}
        for i, (key, value) in enumerate(wordssorted):
            if value == 20:
                break
            self.word2index[key] = i + 4 #PAD,UNK,GO,EOS
        print("Voc size {0}".format(len(self.word2index)))
        self.index2word = dict((v, k) for k, v in self.word2index.items())
        
        #load word vector
        if no_pretrain_word2vec:
            self.vector = None
        else:
            self.vector = 0.1 * np.random.rand(len(self.word2index), dim)
            with open("{0}/vector.txt".format(path)) as fl:
                for line in fl:
                    vec = line.strip().split()
                    word = vec[0].lower()
                    vec = list(map(float, vec[1:]))
                    if word in self.word2index:
                        self.vector[self.word2index[word]] = np.asarray(vec)
            self.vector = torch.Tensor(self.vector)           
           
        #get index
        self.data = {}
        for name in ["train", "valid", "test"]:
            self.data[name] = []
            for item in self.text[name]:
                len_u = len(item[0])
                indices = [[],[[] for _ in range(len_u)],[]] #src_len, src, trg
                indices[0] = [u.count(' ')+1 for u in item[0]] # on purpose
                max_u_len = max(indices[0])
                # history
                for i in range(len_u):
                    words = item[0][i].split()
                    indices[1][i] = [self.word2index[word] if word in self.word2index 
                                  else UNK for word in words] + [PAD] * (max_u_len - len(words))
                # answer
                words = item[1].split()
                indices[2] = [self.word2index[word] if word in self.word2index 
                              else UNK for word in words]
                indices[2].append(EOS)
                self.data[name].append(indices)
           
    def create_dataset(self, name, batch_size):
        datas = self.data[name]
        src_seq_lens = []
        src_seqs, trg_seqs = [], []
        for item in datas:
            src_len, src, trg = item
            tensor_src_len, tensor_src, tensor_trg = torch.LongTensor(src_len), \
                                                    torch.LongTensor(src), torch.LongTensor(trg)
            src_seq_lens.append(tensor_src_len)
            src_seqs.append(tensor_src)
            trg_seqs.append(tensor_trg)
            
        dataset = Dataset(src_seq_lens, src_seqs, trg_seqs)
        dataloader = data.DataLoader(dataset, batch_size, True, collate_fn=pad_packed_collate)
        return dataloader
    
    def interpret(self, preds, refs, lens, f):
        i = random.randrange(0, len(lens))
        l = max(lens)
        for j in range(l):
            word = self.index2word[preds[i][j].item()]
            print(word, end=' ')
            f.write('{0} '.format(word))
            if word == '<EOS>':
                break
        print()
        f.write('\n')
        
        l = lens[i]
        for j in range(l):
            word = self.index2word[refs[i][j].item()] 
            print(word, end=' ')
            f.write('{0} '.format(word))
        print()
        f.write('\n')

class Dataset(data.Dataset):
    
    def __init__(self, src_seq_lens, src_seqs, trg_seqs):
        self.src_seq_lens = src_seq_lens
        self.src_seqs = src_seqs
        self.trg_seqs = trg_seqs
        self.num_total_seqs = len(src_seqs)
        
    def __getitem__(self, index):
        src_seq_len = self.src_seq_lens[index]
        src_seq = self.src_seqs[index]
        trg_seq = self.trg_seqs[index]
        return src_seq_len, src_seq, trg_seq
    
    def __len__(self):
        return self.num_total_seqs
        
def pad_packed_collate(batch_data):
    def merge(sequences):
        lengths = [len(seq) for seq in sequences]
        padded_seqs = torch.zeros(len(sequences), max(lengths)).long()
        for i, seq in enumerate(sequences):
            end = lengths[i]
            padded_seqs[i, :end] = seq
        return padded_seqs, lengths
    
    def hierarchical_merge(sequences, sequence_lengths):
        lengths = torch.stack(sequence_lengths)
        utterance_length = lengths.shape[1]
        padded_seqs = torch.zeros(len(sequences), utterance_length, lengths.max().item()).long()
        for i, seq in enumerate(sequences):
            word_end = max(lengths[i]).item()
            padded_seqs[i, :utterance_length, :word_end] = seq
        return padded_seqs, lengths
    
    # sort a list by sequence length (descending order) to use pack_padded_sequence
    batch_data.sort(key=lambda x: len(x[0]), reverse=True)

    # seperate source and target sequences    
    src_seq_lens, src_seqs, trg_seqs = zip(*batch_data)
    src_seqs, src_lens = hierarchical_merge(src_seqs, src_seq_lens)
    trg_seqs, trg_lens = merge(trg_seqs)
    return (src_seqs.to(device=device), src_lens.to(device=device), 
            trg_seqs.to(device=device), trg_lens)
    