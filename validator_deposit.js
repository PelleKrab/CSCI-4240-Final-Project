// AI assist (copilot)

import { ethers } from "ethers";
import dotenv from "dotenv";

async function main() {
  dotenv.config();

  const privateKey = process.env.PRIVATE_KEY;

  if (!privateKey) {
    throw new Error("PRIVATE_KEY is not set in environment variables");
  }

  const provider = new ethers.JsonRpcProvider("https://rpc.hoodi.ethpandaops.io");
  const wallet = new ethers.Wallet(privateKey, provider);

  const depositContractAddress = "0x00000000219ab540356cBB839Cbe05303d7705Fa";

  const depositAbi = [
    "function deposit(bytes pubkey, bytes withdrawal_credentials, bytes signature, bytes32 deposit_data_root) external payable"
  ];

  const depositContract = new ethers.Contract(depositContractAddress, depositAbi, wallet);

  const pubkey = "0x80036144fcbe30ef66300c7ff0bd3beaab708f50b23ee941645143fda791eddea5b1e8a5e70128a8a0efd02d340a7186";
  const withdrawal_credentials = "0x010000000000000000000000c93a22ffaf410069a064b21db8bfcf2facfbe382";
  const signature = "0x854bc9625f2567582785aa8792df8e601a649aba5223436cacb2d917e25f43f18ec414352cd7a75a947d07f7f77de9ba059fc4686226885ee49bf1647369199db629a6eeca50ee4c283be42da35b85bdacefc6d3567a1e719ffb2fd06adeda00";
  const deposit_data_root = "0x4f8700f759d1b542143d92ea25f7ac809f7a976511340c999d6f804bd37fc748";

  const depositValue = ethers.parseUnits("34", "ether");

  const txRequest = await depositContract.deposit.populateTransaction(
    pubkey,
    withdrawal_credentials,
    signature,
    deposit_data_root,
    { value: depositValue }
  );

  const txResponse = await wallet.sendTransaction(txRequest);
  console.log("Transaction sent. Hash:", txResponse.hash);

  const receipt = await txResponse.wait();
  console.log("Transaction mined in block", receipt.blockNumber);
}

main().catch(console.error);
