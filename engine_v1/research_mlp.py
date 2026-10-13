"""Optional fixed neural research backend. No live model export."""
import numpy as np


def _validate_neural_inputs(train_x, train_y, targets, device, epochs):
    if device not in ('cpu', 'cuda'):
        raise ValueError('Neural device must be cpu or cuda')
    if isinstance(epochs, (bool, np.bool_)) or not isinstance(epochs, (int, np.integer)) or epochs < 1:
        raise ValueError('Neural epochs must be a positive integer')

    def real_array(value, name):
        array = np.asarray(value)
        if array.dtype.kind not in 'fiu' or not np.isfinite(array).all():
            raise ValueError(f'{name} must contain finite real numbers')
        return array

    train_x = real_array(train_x, 'Training features')
    train_y = real_array(train_y, 'Training labels')
    if train_x.ndim != 2 or train_x.shape[0] < 2 or train_x.shape[1] < 1:
        raise ValueError('Training features require at least two rows and one column')
    if train_y.ndim != 1 or len(train_y) != len(train_x):
        raise ValueError('Training labels must be one-dimensional and match feature rows')
    targets = [real_array(t, 'Prediction features') for t in targets]
    if not targets:
        raise ValueError('At least one prediction array is required')
    if any(t.ndim != 2 or t.shape[1] != train_x.shape[1] for t in targets):
        raise ValueError('Prediction features must match training feature columns')
    return train_x, train_y, targets


def fit_predict(train_x, train_y, targets, device='cuda', epochs=40):
    # Validate before importing Torch or allocating GPU memory.
    train_x, train_y, targets = _validate_neural_inputs(train_x, train_y, targets, device, epochs)
    import torch
    torch.set_num_threads(2)
    if device=='cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable; GPU research will not silently use CPU')
    torch.manual_seed(1729)
    mean=train_x.mean(0);scale=train_x.std(0);scale[scale<1e-12]=1
    ym=float(train_y.mean());ys=max(float(train_y.std()),1e-12)
    x=torch.as_tensor((train_x-mean)/scale,dtype=torch.float32,device=device)
    y=torch.as_tensor((train_y-ym)/ys,dtype=torch.float32,device=device).reshape(-1,1)
    net=torch.nn.Sequential(torch.nn.Linear(x.shape[1],32),torch.nn.Tanh(),
        torch.nn.Linear(32,16),torch.nn.Tanh(),torch.nn.Linear(16,1)).to(device)
    opt=torch.optim.AdamW(net.parameters(),lr=.001,weight_decay=.01)
    for epoch in range(epochs):
        order=torch.randperm(len(x),device=device);loss_total=0.
        for ids in order.split(256):
            opt.zero_grad();loss=torch.mean((net(x[ids])-y[ids])**2)
            if not torch.isfinite(loss):raise ValueError('Non-finite neural training loss')
            loss.backward();opt.step();loss_total+=float(loss.detach())*len(ids)
        if epoch==0 or (epoch+1)%10==0:
            print(f'[mlp] device={device} epoch={epoch+1}/{epochs} train_mse_scaled={loss_total/len(x):.6f}',flush=True)
    net.eval()
    with torch.no_grad():
        result=[net(torch.as_tensor((t-mean)/scale,dtype=torch.float32,device=device)).flatten().cpu().numpy().astype(float)*ys+ym for t in targets]
    if any(not np.isfinite(p).all() for p in result):raise ValueError('Non-finite neural predictions')
    return result


def polynomial_predict(train_x, train_y, targets):
    from evaluate_tradeflow import fit_predict as ridge
    mean=train_x.mean(0);scale=train_x.std(0);scale[scale<1e-12]=1
    def expand(x):
        z=(x-mean)/scale
        return np.column_stack([z,*[z[:,i]*z[:,j] for i in range(z.shape[1]) for j in range(i,z.shape[1])]])
    return ridge(expand(train_x),train_y,[expand(t) for t in targets])
