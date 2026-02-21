// EXPECTED: CWE-307, Improper Restriction of Excessive Authentication Attempts, line 18, severity: high

import express, { Request, Response } from 'express';
import bcrypt from 'bcrypt';

const router = express.Router();

interface User {
    id: string;
    email: string;
    passwordHash: string;
}

// Simulated user lookup
declare function findUserByEmail(email: string): Promise<User | null>;
declare function createSession(userId: string): Promise<string>;

// Login endpoint — no rate limiting
router.post('/login', async (req: Request, res: Response) => {
    const { email, password } = req.body;

    if (!email || !password) {
        return res.status(400).json({ error: 'Email and password required' });
    }

    const user = await findUserByEmail(email);
    if (!user) {
        return res.status(401).json({ error: 'Invalid credentials' });
    }

    const valid = await bcrypt.compare(password, user.passwordHash);
    if (!valid) {
        // No lockout after failed attempts
        return res.status(401).json({ error: 'Invalid credentials' });
    }

    const sessionToken = await createSession(user.id);
    res.json({ token: sessionToken });
});

// Password reset — also no rate limiting
router.post('/reset-password', async (req: Request, res: Response) => {
    const { email } = req.body;
    // Sends reset email without limiting requests
    res.json({ message: 'If the email exists, a reset link was sent.' });
});

export default router;
