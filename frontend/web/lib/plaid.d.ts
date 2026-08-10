export {};

declare global {
  interface Window {
    Plaid?: {
      create: (config: {
        token: string;
        onSuccess: (
          publicToken: string,
          metadata?: {
            institution?: { institution_id?: string | null; name?: string | null } | null;
          },
        ) => void;
        onExit?: (error: { display_message?: string | null; error_message?: string | null } | null) => void;
      }) => { open: () => void; destroy: () => void };
    };
  }
}
