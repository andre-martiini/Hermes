
// Mock of the Public Config
const mockPublicConfig = {
    limit: 2000,
    token: 'valid-token-123'
};

const mockTransactions = [
    { id: '1', amount: 100, origin: 'external', date: new Date().toISOString() },
    { id: '2', amount: 50, origin: 'external', date: new Date().toISOString() },
    { id: '3', amount: 500, origin: 'internal', date: new Date().toISOString() }, // Should be ignored
    { id: '4', amount: 2000, origin: 'external', date: '2023-01-01' } // Should be ignored (wrong date)
];

function validateToken(token) {
    return token === mockPublicConfig.token;
}

function calculateSpent(transactions) {
    const now = new Date();
    const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1).toISOString();
    const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString();

    let total = 0;
    transactions.forEach(t => {
        // Logic mimics the server-side query + client-side filter
        if (t.origin === 'external' && t.date >= startOfMonth && t.date <= endOfMonth) {
            total += t.amount;
        }
    });
    return total;
}

// Test Execution
console.log("Running Logic Verification (Secure Architecture)...");

const testToken = 'valid-token-123';
const isValid = validateToken(testToken);
console.log(`Token Validation (${testToken}): ${isValid ? 'PASS' : 'FAIL'}`);

if (!isValid) process.exit(1);

const spent = calculateSpent(mockTransactions);
const expectedSpent = 150; // 100 + 50
console.log(`Spent Calculation: Expected ${expectedSpent}, Got ${spent}`);

if (spent === expectedSpent) {
    console.log("PASS: Logic Verification Successful");
} else {
    console.error("FAIL: Logic Verification Failed");
    process.exit(1);
}
