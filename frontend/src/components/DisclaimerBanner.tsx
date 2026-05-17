import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { alpha, useTheme } from '@mui/material/styles';
import GppGoodOutlinedIcon from '@mui/icons-material/GppGoodOutlined';

export function DisclaimerBanner() {
  const theme = useTheme();
  return (
    <Box
      sx={{
        mx: 'auto',
        maxWidth: 820,
        width: '100%',
        px: { xs: 2, md: 3 },
        pt: 1.5,
      }}
    >
      <Stack
        direction="row"
        spacing={1.25}
        sx={{
          alignItems: 'center',
          px: 1.5,
          py: 1,
          borderRadius: 2,
          bgcolor:
            theme.palette.mode === 'light'
              ? alpha(theme.palette.secondary.main, 0.12)
              : alpha(theme.palette.secondary.main, 0.1),
          border: `1px solid ${alpha(theme.palette.secondary.main, 0.3)}`,
        }}
      >
        <GppGoodOutlinedIcon sx={{ fontSize: 18, color: 'secondary.main' }} />
        <Typography variant="caption" color="textSecondary" sx={{ lineHeight: 1.4 }}>
          Answers are grounded in the official Iowa Code with verifiable links. Always confirm
          before relying on any text — this tool assists, it does not substitute for an attorney's
          judgment.
        </Typography>
      </Stack>
    </Box>
  );
}
