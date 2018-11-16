import time
from tqdm import tqdm
import torch
from torchnet.meter import AverageValueMeter
import torchvision.utils as vutils

from utils.metrics.psnr import PSNR
from optimisation.loss import VGGLoss


def train(args, train_loader, model, criterion, optimizer, epoch, summary_writer):
    # Meters to log batch time and loss
    batch_time_meter = AverageValueMeter()
    loss_meter = AverageValueMeter()

    # Switch to train mode
    model.train()

    end = time.time()
    steps = len(train_loader)
    # Start progress bar. Maximum value = number of batches.
    with tqdm(total=steps) as pbar:
        # Iterate through the training batch samples
        for i, sample in enumerate(train_loader):
            noisy = sample['noisy']
            clean = sample['clean']
            iso = sample['iso']
            # Send inputs to correct device
            noisy = noisy.cuda() if args.cuda else noisy
            clean = clean.cuda() if args.cuda else clean
            iso = iso.cuda() if args.cuda else iso

            # Clear past gradients
            optimizer.zero_grad()

            # Denoise the image and calculate the loss wrt target clean image
            denoised = model(noisy, iso)
            loss = criterion(denoised, clean)

            # Calculate gradients and update weights
            loss.backward()
            optimizer.step()

            # Update meters
            loss_meter.add(loss.item())
            batch_time_meter.add(time.time() - end)
            end = time.time()

            # Write image samples to tensorboard
            if i == 0:
                # TODO: set num_samples_to_log to equal batch size if exceeding it
                if args.train_batch_size >= args.num_samples_to_log:
                    log_images(noisy, denoised, clean, summary_writer,
                               args.num_samples_to_log, (epoch * steps) + i)

            # Update progress bar
            pbar.set_postfix(loss=loss_meter.mean)
            pbar.update()

            # Write the results to tensorboard
            summary_writer.add_scalar('Train/Loss', loss, (epoch * steps) + i)

    average_loss = loss_meter.mean
    print("===> Average total loss: {:4f}".format(average_loss))
    print("===> Average batch time: {:.4f}".format(batch_time_meter.mean))

    return average_loss


def validate(args, val_loader, model, criterion, training_iters, summary_writer):
    """
    Args:
        args: Parsed arguments
        val_loader: Dataloader for validation data
        model: Denoising model
        criterion: Loss function
        training_iters: Number of training iterations elapsed
        summary_writer: Tensorboard summary writer

    Returns:
        Average loss on validation samples
    """
    # Average meters
    batch_time_meter = AverageValueMeter()
    loss_meter = AverageValueMeter()

    # Switch to evaluation mode
    model.eval()

    with torch.no_grad():
        end = time.time()
        steps = len(val_loader)
        # Start progress bar. Maximum value = number of batches.
        with tqdm(total=steps) as pbar:
            # Iterate through the validation batch samples
            for i, sample in enumerate(val_loader):
                noisy = sample['noisy']
                clean = sample['clean']
                iso = sample['iso']
                # Send inputs to correct device
                noisy = noisy.cuda() if args.cuda else noisy
                clean = clean.cuda() if args.cuda else clean
                iso = iso.cuda() if args.cuda else iso

                # Denoise the image and calculate the loss wrt target clean image
                denoised = model(noisy, iso)
                loss = criterion(denoised, clean)

                # Update meters
                loss_meter.add(loss.item())
                batch_time_meter.add(time.time() - end)
                end = time.time()

                # Write image samples to tensorboard
                if i == 0:
                    if args.test_batch_size >= args.num_samples_to_log:
                        log_images(noisy, denoised, clean, summary_writer,
                                   args.num_samples_to_log, training_iters)

                # Update progress bar
                pbar.set_postfix(loss=loss_meter.mean)
                pbar.update()

    average_loss = loss_meter.mean
    # Write average loss to tensorboard
    summary_writer.add_scalar('Test/Loss', average_loss, training_iters)

    print("===> Average total loss: {:4f}".format(average_loss))
    print("===> Average batch time: {:.4f}".format(batch_time_meter.mean))

    return average_loss


def log_images(noisy_image, denoised_image, clean_image,
               summary_writer, n_samples, training_iters):
    summary_writer.add_image(
        'noisy_images', vutils.make_grid(noisy_image.data[:n_samples], normalize=True,
                                         scale_each=True), training_iters)
    summary_writer.add_image(
        'denoised_images', vutils.make_grid(denoised_image.data[:n_samples], normalize=True,
                                            scale_each=True), training_iters)
    summary_writer.add_image(
        'clean_images', vutils.make_grid(clean_image.data[:n_samples], normalize=True,
                                         scale_each=True), training_iters)


def evaluate_psnr_and_vgg_loss(args, model, data_loader):
    # Average meters
    batch_time_meter = AverageValueMeter()
    psnr_meter = AverageValueMeter()
    vgg_loss_meter = AverageValueMeter()

    psnr_calculator = PSNR(data_range=1)
    vgg_loss_calculator = VGGLoss(args)
    if args.cuda:
        psnr_calculator.cuda()
        vgg_loss_calculator.cuda()

    # Switch to evaluation mode
    model.eval()

    with torch.no_grad():
        end = time.time()
        steps = len(data_loader)
        # Start progress bar. Maximum value = number of batches.
        with tqdm(total=steps) as pbar:
            # Iterate through the validation batch samples
            for i, sample in enumerate(data_loader):
                noisy = sample['noisy']
                clean = sample['clean']
                iso = sample['iso']
                # Send inputs to correct device
                noisy = noisy.cuda() if args.cuda else noisy
                clean = clean.cuda() if args.cuda else clean
                iso = iso.cuda() if args.cuda else iso

                # Denoise the image and calculate the loss wrt target clean image
                denoised = model(noisy, iso)
                psnr = psnr_calculator(denoised, clean).mean()
                vgg_loss = vgg_loss_calculator(denoised, clean)

                # Update meters
                psnr_meter.add(psnr.item())
                vgg_loss_meter.add(vgg_loss.item())

                batch_time_meter.add(time.time() - end)
                end = time.time()

                # Update progress bar
                pbar.set_postfix(psnr=psnr_meter.mean)
                pbar.set_postfix(ssim=vgg_loss_meter.mean)
                pbar.update()

    average_psnr = psnr_meter.mean
    average_vgg_loss = vgg_loss_meter.mean
    # Write average loss to tensorboard
    print("===> Average PSNR score: {:4f}".format(average_psnr))
    print("===> Average VGG loss: {:4f}".format(average_vgg_loss))
    print("===> Average batch time: {:.4f}".format(batch_time_meter.mean))
    # TODO: Save results to a csv/text file

    return average_psnr, average_vgg_loss
