export {};

declare global {
  interface Window {
    Plaid?: {
      create: (config: {
        token: string;
        onSuccess: (publicToken: string) => void;
        onExit?: (error: { display_message?: string | null; error_message?: string | null } | null) => void;
      }) => { open: () => void; destroy: () => void };
    };
  }
}
