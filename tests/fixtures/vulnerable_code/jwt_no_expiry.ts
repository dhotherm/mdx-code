// EXPECTED: CWE-613, Insufficient Session Expiration, line 20, severity: high

import jwt from 'jsonwebtoken';
import { Request, Response, NextFunction } from 'express';

const SECRET_KEY = process.env.JWT_SECRET || 'default-secret';

interface TokenPayload {
    userId: string;
    role: string;
}

export function generateToken(userId: string, role: string): string {
    const payload: TokenPayload = { userId, role };
    // Token generated without expiration — lives forever
    return jwt.sign(payload, SECRET_KEY);
}

export function verifyToken(req: Request, res: Response, next: NextFunction): void {
    const token = req.headers.authorization?.split(' ')[1];

    if (!token) {
        res.status(401).json({ error: 'No token provided' });
        return;
    }

    try {
        // No expiration check — expired tokens are accepted
        const decoded = jwt.verify(token, SECRET_KEY) as TokenPayload;
        (req as any).user = decoded;
        next();
    } catch (err) {
        res.status(401).json({ error: 'Invalid token' });
    }
}

export function refreshToken(oldToken: string): string {
    const decoded = jwt.decode(oldToken) as TokenPayload;
    // Re-signing without expiration again
    return jwt.sign({ userId: decoded.userId, role: decoded.role }, SECRET_KEY);
}
