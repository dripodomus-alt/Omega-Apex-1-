import { ethers, ContractFactory } from 'ethers';
import * as fs from 'fs/promises';
import * as path from 'path';
import 'dotenv/config'; // Automatically load .env file

// In a real project, these would be imported from a '@omega/contracts' package
// after the contracts have been compiled by Hardhat or Foundry.
const AAVE_ADAPTER_ARTIFACT = {
  abi: ["constructor()", "function ADAPTER_NAME() view returns (string)"],
  bytecode: '0x608060405234801561001057600080fd5b50600080546001600160a01b0319163317905561010060025560c0806100366000396000f3fe6080604052348015600f57600080fd5b506004361060285760003560e01c8063b100b26614602d575b600080fd5b60336045565b604051603e91906067565b60405180910390f35b600080546001600160a01b03163314606257600080fd5b60005490565b600080546001600160a01b0319166001600160a01b039290921691909117905556fea2646970667358221220ec71239148a08a282d689d9de579e952b61f881ea4244c92473b125543d8434a64736f6c63430008180033',
};
const BALANCER_ADAPTER_ARTIFACT = {
    abi: ["constructor()", "function ADAPTER_NAME() view returns (string)"],
    bytecode: '0x608060405234801561001057600080fd5b50600080546001600160a01b0319163317905561010060025560c0806100366000396000f3fe6080604052348015600f57600080fd5b506004361060285760003560e01c8063b100b26614602d575b600080fd5b60336045565b604051603e91906067565b60405180910390f35b600080546001600160a01b03163314606257600080fd5b60005490565b600080546001600160a01b0319166001600160a01b039290921691909117905556fea2646970667358221220ec71239148a08a282d689d9de579e952b61f881ea4244c92473b125543d8434a64736f6c63430008180033',
};

/**
 * Updates the .env file with the deployed contract addresses.
 * This function is idempotent and will either update existing lines or append new ones.
 */
async function updateEnvFile(updates: Record<string, string>) {
  const envPath = path.resolve(process.cwd(), '../../.env');
  let content = '';
  try {
    content = await fs.readFile(envPath, 'utf-8');
  } catch (e) {
    console.warn(`[WARN] .env file not found at ${envPath}. A new one will be created.`);
  }

  for (const [key, value] of Object.entries(updates)) {
    const regex = new RegExp(`^${key}=.*`, 'm');
    if (content.match(regex)) {
      content = content.replace(regex, `${key}=${value}`);
    } else {
      content += `\n${key}=${value}`;
    }
  }

  await fs.writeFile(envPath, content);
  console.log(`✅ .env file updated with new contract addresses.`);
}

async function main() {
  console.log('🚀 Starting OMEGA-FINALLY-RICH Adapter Deployment Script...');

  // 1. Get configuration from environment
  const rpcUrl = process.env.BROADCAST_RPC_URL;
  const privateKey = process.env.EXECUTOR_PRIVATE_KEY;

  if (!rpcUrl || !privateKey) {
    throw new Error('BROADCAST_RPC_URL and EXECUTOR_PRIVATE_KEY must be set in your .env file.');
  }

  // 2. Set up provider and wallet
  const provider = new ethers.JsonRpcProvider(rpcUrl);
  const wallet = new ethers.Wallet(privateKey, provider);
  const network = await provider.getNetwork();

  console.log(`\nDeploying to network: ${network.name} (Chain ID: ${network.chainId})`);
  console.log(`Using deployer address: ${wallet.address}`);
  const balance = await provider.getBalance(wallet.address);
  console.log(`Deployer balance: ${ethers.formatEther(balance)} MATIC`);

  // 3. Deploy contracts
  const deployedAddresses: Record<string, string> = {};

  console.log('\nDeploying AaveV3CapitalSourceAdapter...');
  const aaveFactory = new ContractFactory(AAVE_ADAPTER_ARTIFACT.abi, AAVE_ADAPTER_ARTIFACT.bytecode, wallet);
  const aaveAdapter = await aaveFactory.deploy();
  await aaveAdapter.waitForDeployment();
  const aaveAddress = await aaveAdapter.getAddress();
  deployedAddresses['AAVE_V3_CAPITAL_ADAPTER'] = aaveAddress;
  console.log(`   -> AaveV3CapitalSourceAdapter deployed at: ${aaveAddress}`);

  console.log('Deploying BalancerVaultCapitalSourceAdapter...');
  const balancerFactory = new ContractFactory(BALANCER_ADAPTER_ARTIFACT.abi, BALANCER_ADAPTER_ARTIFACT.bytecode, wallet);
  const balancerAdapter = await balancerFactory.deploy();
  await balancerAdapter.waitForDeployment();
  const balancerAddress = await balancerAdapter.getAddress();
  deployedAddresses['BALANCER_VAULT_CAPITAL_ADAPTER'] = balancerAddress;
  console.log(`   -> BalancerVaultCapitalSourceAdapter deployed at: ${balancerAddress}`);

  // 4. Write addresses back to .env file
  await updateEnvFile(deployedAddresses);

  console.log('\n🎉 Adapter deployment and configuration complete!');
}

main().catch((error) => {
  console.error('\n❌ Deployment failed:', error);
  process.exit(1);
});